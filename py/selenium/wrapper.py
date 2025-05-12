# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import logging
import os
import re
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from enum import Enum
from io import BytesIO
from typing import NamedTuple

import sh
from django.utils.http import urlencode
from PIL import Image
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from olib.py.django.test.debug import breakOnError, breakOnErrorCheckpoint
from olib.py.selenium.browser import BrowserNames, SeleniumBrowser
from olib.py.utils.lazy import lazyReCompile
from olib.py.utils.wait import waitFor

logger = logging.getLogger(__name__)


class WaitForPageLoad:
    """Launch a new page within this monitor to wait for the page to load before returning"""

    # https://www.develves.net/blogs/asd/2017-03-04-selenium-waiting-for-page-load/
    SET_ALL_IMAGES_LOADED_SCRIPT = """
        // TODO: this should probably query for and handle elements with background images as well.
        (function() {
            const allPageImages = Array.from(document.querySelectorAll('img'))
            if (!allPageImages.length) {
                // there are no images on the page.
                window._olib_allImagesLoaded = true
            } else {
                Promise.all(allPageImages.map(img => new Promise((resolve, reject) => {
                    // create and load a new image using img.src. This shouldn't have a large overhead because of browser caching
                    const image = new Image()
                    image.onload = function () {
                        requestAnimationFrame(function () {
                            requestAnimationFrame(function() {
                                resolve(image)
                            })
                        })
                    }
                    image.onerror = function(e) {
                        resolve(image)
                    }
                    image.src = img.src
                }))).then(images => {
                    //console.log(images)
                    window._olib_allImagesLoaded = true
                });
            }
        })()
    """

    def __init__(self, base, timeout=5, waitForFullLoad=False, processLog=True, ignore404=False):
        self.base = base
        self.timeout = timeout
        self.waitForFullLoad = waitForFullLoad
        self.loadImagesScriptRan = False
        self.old_page = None
        self.errors = []
        self.processLog = processLog
        self.ignore404 = ignore404

    def __enter__(self):
        try:
            self.old_page = self.base.selenium.find_element(By.TAG_NAME, 'html')
        except:  # pylint: disable=bare-except
            # Old page stays at None. Accept any new page as a next page
            logger.info('unable to find old page')

    def __exit__(self, ex_type, ex_val, tb):
        if ex_val is not None:
            # Exception was railed in context.. Cannot re-raise, but rather raise our own
            raise Exception('WaitForPageLoad context failed')

        conditionFunction = (
            lambda: self.newPageLoadComplete()
            and self.contentLoadComplete()
            and (not self.waitForFullLoad or self.pageHasFullyLoaded())
        )
        self.wait_for(conditionFunction)

    def wait_for(self, condition_function):
        start_time = time.time()
        while time.time() < start_time + self.timeout or self.base.disableTimeouts:
            if self.processLog:
                self.base.processConsoleLog()
            if condition_function():
                return True
            time.sleep(0.1)

        if self.errors:
            logger.error(f"Got errors: {', '.join(self.errors)}")
            breakOnErrorCheckpoint()

        with breakOnError():
            raise Exception(
                f"Timeout of {self.timeout} seconds expired waiting for {condition_function.__name__} on url {self.base.selenium.current_url}"
            )

    def waitForPageLoadToComplete(self):
        """Call after page-load to ensure that everything has loaded. Does 2 last steps of load checks. Does not check for transition to new page"""
        self.wait_for(lambda: self.contentLoadComplete() and (not self.waitForFullLoad or self.pageHasFullyLoaded()))

    def executeSetAllImagesLoadedScript(self):
        """
        Run a script to set window._olib_allImagesLoaded once all images currently on the page have loaded.
        Note: this will fire before the images have finished painting.
        """
        return self.base.selenium.execute_script(WaitForPageLoad.SET_ALL_IMAGES_LOADED_SCRIPT)

    def waitForPageLoadComplete(self):
        start = time.time()
        logger.info('Waiting for page load completion')
        self.wait_for(self.contentLoadComplete)
        logger.info(f"Done waiting for page load completion ({time.time() - start} seconds)")

    def newPageLoadComplete(self):
        try:
            new_page = self.base.selenium.find_element(By.TAG_NAME, 'html')
        except:  # pylint: disable=bare-except
            return False

        if self.old_page is None or new_page.id != self.old_page.id:
            # Check that javascript is also done setting stuff up
            return self.contentLoadComplete()
        return False

    def contentLoadComplete(self):
        state = self.base.selenium.execute_script(
            'return (document.readyState == "complete") ? (window._olib_loaded === undefined ? "loaded" : (window._olib_loaded === true ? "olib-loaded" : (window._olib_failed === true ? "olib-error" : "olib-not-loaded"))) : "not-loaded"'
        )

        complete = False

        if state in ('olib-loaded', 'loaded'):
            logger.info(f"** completed: {state}")
            complete = True

        if state in ('olib-error',):
            logger.error(f"** completed with error: {state}")
            self.errors.append('olib-error')
            complete = True

        if complete:
            if not self.ignore404:
                # See if we hit 404
                h1 = self.base.element('h1', raiseOnNotFound=False)
                if h1 is not None and '404' in h1.text:
                    logger.error(f"** hit 404 when waiting for page load on URL {self.base.selenium.current_url}")
                    self.errors.append('404')

        return complete

    def pageHasFullyLoaded(self):
        """
        Uses selenium to execute javascript to check if all images have loaded.
        """
        if not self.loadImagesScriptRan:
            self.executeSetAllImagesLoadedScript()
            self.loadImagesScriptRan = True
            return False

        # run a script to check if window._olib_allImagesLoaded is true
        checkAllImagesLoadedScript = 'return !!window._olib_allImagesLoaded && document.readyState === "complete"'
        imagesFinishedLoading = self.base.selenium.execute_script(checkAllImagesLoadedScript)
        return imagesFinishedLoading


class OWebElement:
    """WebElement wrapper to add enhanced functionality for web elements. Primarily break-on-error"""

    def __init__(self, element):
        self._element = element  # Wrapped element

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return getattr(self, attr)

        return getattr(self._element, attr)

    @breakOnError()
    def click(self):
        self._element.click()

    @breakOnError()
    def send_keys(self, *value):
        self._element.send_keys(*value)

    def getParent(self):
        return OWebElement(self.find_element(By.XPATH, '..'))


class Res(Enum):
    phone = 'phone'
    tablet = 'tablet'
    landscape = 'landscape'
    laptop = 'laptop'
    desktop = 'desktop'

    phoneTall = 'phoneTall'
    tabletTall = 'tabletTall'


class BrowserRes(NamedTuple):
    width: int
    height: int
    name: Res
    mockHeight: int | None = None

    @property
    def resName(self):
        return f"{self.width}x{self.mockHeight if self.mockHeight is not None else self.height}"


class SeleniumWrapper:
    # Errors that are filtered out from browser log
    filterErrors = {
        'network': [
            lazyReCompile(
                r'about:blank - Failed to load resource:\s+net::ERR_UNKNOWN_URL_SCHEME',
                re.S,
            ),  # Don't know why this happens, but seems unrelated to app
        ],
    }

    # Limit snaps by default
    defaultResolution = Res.laptop

    host = '127.0.0.1'  # Config for LiveServerTestCase to ensure cookies are on correct domain

    class WaitCondition(Enum):
        presence = 0
        clickable = 1
        selected = 2
        enabled = 3

    def __init__(self, debugDelay=0, disableTimeouts=False):
        self.debugDelay = debugDelay
        self.waitDelay = 45 if not disableTimeouts else 36000
        self.requestTimeout = 30 if not disableTimeouts else 36000

        self.capturedLog = []  # Will fill up with captured log items. Tests can clear at will

        self._selenium = None
        self.downloadDir = None

        self.testDefaultResolution = None
        self.currentResolution = None

    @property
    def selenium(self):
        if self._selenium is None:
            raise Exception('Must create browser before using selenium functions')

        return self._selenium

    def getBrowserName(self):
        return self.selenium.name

    def getBrowserWindowSize(self, outputFormat='string'):
        currentWindowSize = self.selenium.get_window_size()
        if outputFormat != 'string':
            return currentWindowSize
        return f"{currentWindowSize['width']},{currentWindowSize['height']}"

    def setResolution(
        self,
        resolution: Res | BrowserRes | tuple[int, int] | None = None,
        setSizeOfViewport: bool = True,
        setTestDefault: bool = False,
    ) -> None:
        """
        By default sets the viewport size, pass setSizeOfViewport=False to set window size.
        When in non-headless mode, the minimum size settable might be restricted.

        Chrome:
            GUI:
                Window: 508, 133
                Viewport: 500, 2
            HEADLESS:
                no minimum
        Firefox:
            GUI:
                Window: 300, 99
                Viewport: 300, 25
            HEADLESS:
                same as with gui
        """
        if resolution is None:
            # Opt for default resolution
            resolution = (
                self.testDefaultResolution if self.testDefaultResolution is not None else self.defaultResolution
            )

        if setTestDefault:
            self.testDefaultResolution = resolution

        _resolution = resolution

        if _resolution == self.currentResolution:
            # No need to update resolution
            return

        if setSizeOfViewport:
            # this will set the size of the viewport instead of the window
            windowSize = self.selenium.execute_script(
                'return [window.outerWidth - window.innerWidth + arguments[0], window.outerHeight - window.innerHeight + arguments[1]]',
                *_resolution,
            )
        else:
            windowSize = _resolution

        self.selenium.set_window_size(*_resolution)
        time.sleep(0.5)  # Give things some time to settle

        self.currentResolution = windowSize

    def setBrowser(
        self,
        browserName: str = BrowserNames.CHROME,
        blockUrls: bool = True,
        gui: bool = True,
        devtools: bool = False,
        maximized: bool = False,
        userProfile: bool = False,
    ) -> None:
        self._selenium, self.downloadDir = SeleniumBrowser.getBrowser(
            browserName,
            blockUrls=blockUrls,
            gui=gui,
            devtools=devtools,
            maximized=maximized,
            userProfile=userProfile,
        )

        logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.INFO)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)

    def clearDownloads(self):
        """Clear all current browser downloads"""
        sh.rm('-f', f"{self.downloadDir}/*")

    def getDownloads(self, filterFunc=None):
        """Returns list of downloaded files. Filters out files in progress"""
        return [
            f"{root}/{filename}"
            for root, _, files in os.walk(self.downloadDir)
            for filename in files
            if not filename.endswith('crdownload') and filterFunc is None or filterFunc(filename)
        ]

    def goto(
        self,
        url,
        args=None,
        pageLoadWaitTimeout=60,
        pageLoadWait=True,
        processLog=True,
        ignore404=False,
        disableBreakOnError=False,
    ):
        """
        Go to the given URL. Waits for transition to complete before moving on
        """
        urlParams = '?' + urlencode(args) if args else ''
        fullUrl = url + urlParams

        if self.debugDelay:
            time.sleep(self.debugDelay)

        logger.info(f"SELENIUM GOTO: {fullUrl}")

        if pageLoadWait:
            with WaitForPageLoad(self, pageLoadWaitTimeout, processLog=processLog, ignore404=ignore404):
                try:
                    # Selenium seems to time out sometimes when going to a URL.. If this happens, retry
                    attempts = 2
                    while attempts > 0:
                        try:
                            self.selenium.get(fullUrl)
                            break
                        except TimeoutException as e:
                            attempts -= 1
                            print(f"***hit selenium page timeout on {fullUrl}")
                            if not attempts:
                                raise Exception('Timed out multiple times') from e

                except Exception as e:  # pylint: disable=broad-exception-caught
                    if not disableBreakOnError:
                        if not breakOnErrorCheckpoint(e):
                            raise
        else:
            self.selenium.get(fullUrl)

        if processLog:
            self.processConsoleLog()

    def element(self, *args, **kwargs):
        """Get element by optional method. At least one of the parameters of the function must be used"""
        elements = self.elements(*args, **{**kwargs, 'maxItems': 1})

        return elements[0] if elements else None

    def hasElement(self, *args, **kwargs):
        return self.element(*args, **kwargs, raiseOnNotFound=False) is not None

    def elements(
        self,
        selector: str | None = None,
        name: str | None = None,
        tag: str | None = None,
        xpath: str | None = None,
        id: str | None = None,  # pylint: disable=redefined-builtin
        linkText: str | None = None,
        parent: OWebElement | None = None,
        condition: Callable | 'WaitCondition' | list[Callable | 'WaitCondition'] | None = None,
        raiseOnNotFound: bool = True,
        disableBreakOnError: bool = False,
        maxItems: int = -1,
    ) -> list[OWebElement]:
        """Get elements by optional method. At least one of the parameters of the function must be used"""
        if self.debugDelay:
            time.sleep(self.debugDelay)

        parent = parent or self.selenium
        if isinstance(parent, OWebElement):
            parent = parent._element  # pylint: disable=protected-access

        elements = []

        assert parent is not None  # Parent should be defined at this point # nosec

        try:
            if name is not None:
                # Get by name
                elements = parent.find_elements(By.NAME, name)
            elif tag is not None:
                elements = parent.find_elements(By.TAG_NAME, tag)
            elif selector is not None:
                elements = parent.find_elements(By.CSS_SELECTOR, selector)
            elif xpath is not None:
                elements = parent.find_elements(By.XPATH, xpath)
            elif id is not None:
                elements = parent.find_elements(By.ID, id)
            elif linkText is not None:
                elements = parent.find_elements(By.LINK_TEXT, linkText)
            else:
                raise Exception('Must pass one param')
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Help ourself capture any console errors that might have caused us to not find the item
            self.processConsoleLog()
            if raiseOnNotFound:
                if not disableBreakOnError:
                    if not breakOnErrorCheckpoint(e):
                        raise
                else:
                    raise

        if condition:
            conditions = (
                () if condition is None else ((condition,) if not isinstance(condition, (list, tuple)) else condition)
            )
            newElements = []

            for element in elements:
                passed = True
                for cond in conditions:
                    if cond == self.WaitCondition.presence:
                        pass
                    elif cond == self.WaitCondition.clickable:
                        passed &= element.is_enabled() and element.is_displayed()
                    elif cond == self.WaitCondition.selected:
                        passed &= element.is_selected()
                    elif cond == self.WaitCondition.enabled:
                        passed &= element.is_enabled()
                    elif callable(cond):
                        passed &= cond(element)

                if passed:
                    newElements.append(element)

            elements = newElements

        if not elements and raiseOnNotFound:
            if not disableBreakOnError:
                if not breakOnErrorCheckpoint():
                    raise Exception('Could not find element')
            else:
                raise Exception('Could not find element')

        elif elements and -1 > maxItems > len(elements):
            raise Exception('Expected max {maxItems} items. Found {len(elements)}.')

        return [OWebElement(element) for element in elements]

    # REMOVE
    def waitFor(self, *args, **kwargs):
        """Same as utils.waitFor, but allows breakpoint on failed wait"""
        waitFor(*args, **kwargs)

    def waitForUrl(
        self,
        url,
        args=None,
        match='endswith',
        processLog=True,
        waitForPageLoad=True,
        waitForever=False,
        testCount=1,
        testDelaySeconds=0.5,
    ):
        """Waits until the given `url` string can be found inside the browser URL"""
        if self.debugDelay:
            time.sleep(self.debugDelay)

        logger.info(f"SELENIUM WAIT-URL: {url}")

        urlParams = '?' + urlencode(args) if args else ''
        fullUrl = url + urlParams

        matchFunc = None
        if match == 'exact':
            matchFunc = lambda s, url: url == s
        elif match == 'in':
            matchFunc = lambda s, url: url in s
        elif match == 'startswith':
            matchFunc = lambda s, url: s.startswith(url)
        elif match == 'endswith':
            matchFunc = lambda s, url: s.endswith(url)
        elif match == 'regex':
            matchFunc = lambda s, url: bool(re.search(url, s))
        else:
            raise Exception(f"invalid match function: {match}")

        first = True
        for _ in range(testCount):
            if not first:
                time.sleep(testDelaySeconds)
            else:
                first = False

            try:
                # Test for a couple conditions:
                # - URL is correct URL
                # - document load complete
                # - in case of userview, userview loaded
                WebDriverWait(self.selenium, 10 * 3600 if waitForever else self.waitDelay).until(
                    lambda x: matchFunc(x.current_url, fullUrl)
                    and x.execute_script(
                        'return document.readyState == "complete" && (window._olib_loaded === undefined || window._olib_loaded === true)'
                    )
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.processConsoleLog()  # Expose any JS errors that might have caused us to not get to the right page
                with breakOnError():
                    raise Exception(
                        f"Timeout waiting for URL `{fullUrl}`, found URL `{self.selenium.current_url}`"
                    ) from e

            if waitForPageLoad:
                # Make sure page is completely loaded
                WaitForPageLoad(self).waitForPageLoadComplete()

            if processLog:
                self.processConsoleLog()

        logger.info(f"SELENIUM WAIT-URL DONE: {url}")

    def waitForConsoleLog(self, textRegex):
        """Wait for given regex to match any browser log messages. WILL CLEAR CAPTUREDLOG while searching"""
        reg = re.compile(textRegex) if isinstance(textRegex, str) else textRegex

        def check():
            # Capture log entries
            self.processConsoleLog()
            if any(reg.match(l) for l in self.capturedLog):
                return True

            self.capturedLog = []
            return False

        self.waitFor(check)

    def waitForElement(
        self,
        selector: str | None = None,
        name: str | None = None,
        xpath: str | None = None,
        id: str | None = None,
        parent: OWebElement | None = None,
        condition: Callable | 'WaitCondition' | list[Callable | 'WaitCondition'] | None = None,
        errorMsg: str = '',
        waitDelay: float | None = None,
        extraDelay: float | None = None,
        raiseOnNotFound: bool = True,
    ) -> OWebElement | None:
        """Waits for element to have a condition. Same syntax as SeleniumBase.element(..)
        condition: 'presence', 'selected', 'clickable'
        """
        waitDelay = max(waitDelay or 0, self.waitDelay)

        if self.debugDelay:
            time.sleep(self.debugDelay)

        def conditionFunc():
            return self.elements(
                selector=selector,
                name=name,
                xpath=xpath,
                id=id,
                parent=parent,
                condition=condition,
                disableBreakOnError=True,
                raiseOnNotFound=False,
                maxItems=1,
            )

        tStart = time.time()
        elements = waitFor(
            conditionFunc,
            timeout=waitDelay,
            extraDelay=extraDelay,
            raiseOnFailure=False,
            description='waitForElement()',
        )

        if not elements:
            self.processConsoleLog()  # Expose any JS errors that might have caused us to not get the right element
            elapsed = round(time.time() - tStart)
            if raiseOnNotFound:
                with breakOnError():
                    raise Exception(f"Unable to find element after {elapsed} seconds. {errorMsg}")
            return None

        return elements[0]

    def waitForAlert(self, text, accept=True):
        """Waits for alert, then clicks OK if accept is True, else cancel"""
        waitDelay = 3
        WebDriverWait(self.selenium, waitDelay).until(EC.alert_is_present(), text)

        alert = self.selenium.switch_to.alert
        alert.accept()
        logger.info('alert accepted')

    def waitForScriptCallback(self, script, *args):
        """Executes script and waits for callback to be called. Put $$ in script where callback should be placed"""
        if '$$' not in script:
            raise Exception('make sure to use $$ in the place where a callback function should be put in the script')

        modScript = """
            window.__waitForScriptCallback_done = false;
            function _waitForScriptCallback_callback() {
               window.__waitForScriptCallback_done = true;
            };
        """ + script.replace(
            '$$', '_waitForScriptCallback_callback'
        )

        self.selenium.execute_script(modScript, *args)
        self.waitFor(lambda: self.selenium.execute_script('return window.__waitForScriptCallback_done;'))

    def waitDebugDly(self):
        """Waits if debugDelay is set"""
        if self.debugDelay:
            time.sleep(self.debugDelay)

    def mountScrollMonitor(self):
        """Must be called before calls to waitForScroll on a new window"""
        self.selenium.execute_script(
            """
            if (window.scrollingStopped === undefined) {
                //Setup fast scrolling
                //Create style tag
                var style = document.createElement("style")
                style.appendChild(document.createTextNode("")); //WebKit hack
                document.head.appendChild(style);

                //Add rules
                style.sheet.insertRule("* {scroll-behavior: auto; }", 0);


                // Setup isScrolling variable
                var isScrolling;
                window.scrollingStopped = true;

                // Listen for scroll events
                window.addEventListener('scroll', function ( event ) {
                    //console.log('Scroll started', window.scrollY);
                    window.scrollingStopped = false;
                    // Clear our timeout throughout the scroll
                    window.clearTimeout( isScrolling );

                    // Set a timeout to run after scrolling ends
                    isScrolling = setTimeout(function() {

                    // Run the callback
                    //console.log('Scrolling has stopped.');
                    window.scrollingStopped = true;

                    }, 100);

                }, false);
            }
            """
        )

    def waitForScroll(self, scrolling=False):
        """Waits until scrolling has stopped"""

        if self.selenium.execute_script('return window.scrollingStopped === undefined;'):
            raise Exception('Must call mountScrollMonitor before waiting for scrolling')

        WebDriverWait(self.selenium, 60).until(
            lambda x: scrolling ^ x.execute_script('return window.scrollingStopped;')
        )

    def scrollTo(self, element):
        if self.selenium.execute_script('return window.scrollingStopped === undefined;'):
            self.mountScrollMonitor()
            time.sleep(0.5)

        # Scroll until item is in view
        while True:
            if self.isElementInViewport(element):
                return element

            # Scroll to element
            self.selenium.execute_script(
                'arguments[0].scrollIntoView({block: "center", scrollBehavior: "auto"})',
                element._element,  # pylint: disable=protected-access
            )
            time.sleep(0.3)
            self.waitForScroll()

    def isElementInViewport(self, element):
        return bool(
            self.selenium.execute_script(
                'var elem = arguments[0],                 '
                + '  box = elem.getBoundingClientRect(),    '
                + '  cx = box.left + box.width / 2,         '
                + '  cy = box.top + box.height / 2,         '
                + '  e = document.elementFromPoint(cx, cy); '
                + 'for (; e; e = e.parentElement) {         '
                + '  if (e === elem)                        '
                + '    return true;                         '
                + '}                                        '
                + 'return false;                            ',
                element._element,  # pylint: disable=protected-access
            )
        )

    def replaceInputText(self, element, text):
        """Robustly deletes existing text and enters the new text. Selenium can be a bit tricky here, so do it in a loop, verifying that clean before entering new text"""

        def getVal():
            _v = element.get_attribute('value')
            logger.info(f"replace cur: {_v}, target: {text}")
            return _v

        val = getVal()
        while val != text:
            # Clear input
            while val != '':
                element.send_keys(Keys.LEFT_CONTROL + 'a')
                element.send_keys(Keys.DELETE)
                val = getVal()

            # Should now be clear.. set val
            element.send_keys(text)

            # Then read back to verify we got it
            val = getVal()

    def getCookiesDict(self):
        return {c['name']: c['value'] for c in self.selenium.get_cookies()}

    def clearCookies(self):
        """Only deletes cookies for the current domain"""
        logger.info('delete_all_cookies')
        self.selenium.delete_all_cookies()

    def getQueryStringParam(self, name):
        params = self.selenium.current_url.split('?')[1]

        for p in params.split('&'):
            n, v = p.split('=')
            if n == name:
                return v
        return ''

    def processConsoleLog(self):
        """Goes through all current web console log items and highlights errors as errors"""
        # geckodriver (firefox) does not support the logging API currently. https://github.com/mozilla/geckodriver/issues/284#issuecomment-458305621
        # https://github.com/hurracom/WebConsoleTap a js library that tries to remedy this
        if self.getBrowserName() == 'firefox':
            return True  # No log items we know about. Success! :p

        # Get in-browser log, to look for issues
        log = self.selenium.get_log('browser')

        # Filter out non-important stuff (convert them to IGNORE)
        filters = self.filterErrors

        for l in log:
            if l['level'] in ('SEVERE', 'ERROR', 'WARNING'):
                # print(f'source: {l["source"]} - message: {l["message"]}')
                # breakpoint()
                if l['source'] in filters and any(r.search(l['message']) for r in filters[l['source']]):
                    l['level'] = 'IGNORED'

            # Parse log message.
            #  loc = e.g. 10:99, meaning line 10, position 99.
            #  text has multiple values, e.g. "hoho %s" "ya\\"", and the 1+ values are parameters to the first, replacing the %s
            path, loc, text = l['message'].split(' ', maxsplit=2)

            # Dirty hack to exclude escaped quotes items when splitting text by "
            if text.startswith('"'):
                textItems = [
                    t.replace('!@#', '"').replace('\\n', '\n').replace('{', '{{').replace('}', '}}').replace('%s', '{}')
                    for t in text.replace('\\"', '!@#').split('" "')
                ]
                textItems[0] = textItems[0][1:]  # exclude starting and ending "
                textItems[-1] = textItems[-1][:-1]
                text = textItems[0].format(*textItems[1:])

            message = f"BROWSER log: Chrome {l['source']} [{l['level']}] {path}:{loc}: {text}"
            logLevel = logging.ERROR if l['level'] in ('SEVERE', 'ERROR', 'WARNING') else logging.INFO
            logger.log(logLevel, message)
            self.capturedLog.append(message)

        webSevere = any(l['level'] == 'SEVERE' for l in log)
        webError = any(l['level'] == 'ERROR' for l in log)
        webWarning = any(l['level'] == 'WARNING' for l in log)

        if webSevere or webError or webWarning:
            errorType = f"Web Log {'SEVERE' if webSevere else 'ERROR' if webError else 'WARNING'}"
            logger.error(f"severe web error ^: {errorType}")

            return False

        return True

    def debugScreenshot(self, middleName='debug'):
        path = f"./output/selenium-{middleName}-screenshot-{uuid.uuid4()}"
        self.selenium.get_screenshot_as_file(f"{path}.png")
        with open(f"{path}.html", 'w', encoding='utf-8') as f:
            f.write(self.selenium.page_source)

        print(
            f"SELENIUM {middleName.upper()}\n"
            + f"  SCREENSHOT: {path}.png\n"
            + f"  URL: {self.selenium.current_url}\n"
            + f"  SRC: {path}.html"
        )
        return path

    @contextmanager
    def initBrowserTest(self, browserName, resolution):
        """Manages current browser/resolution"""
        self.setBrowser(browserName, resolution)
        yield
        self.setBrowser()

    def getTotalPageHeight(self):
        return self.selenium.execute_script(
            'return Math.max(document.body.scrollHeight, document.body.offsetHeight, document.documentElement.clientHeight, document.documentElement.scrollHeight, document.documentElement.offsetHeight);'
        )

    def scrollToPosition(self, x=0, y=0):
        self.selenium.execute_script(f"window.scrollTo({x}, {y})")

    def getFullScreenshot(self, scroll=True):
        """
        Gets a screenshot of the entire page. Takes screenshots of the page while scrolling before stitching them into one image.
        :return: Screenshot in the form of a PIL.Image in 'RGB' format
        """
        imageSlices = []
        offset = 0
        offsets = []

        # Reset, in case the test has moved around the page
        self.scrollToPosition()
        time.sleep(0.2)

        totalPageHeight = self.getTotalPageHeight()
        viewportHeight = self.selenium.execute_script('return window.innerHeight')

        # while we haven't reached the bottom of the page
        while offset < totalPageHeight:
            if offset > 0 and (offset + viewportHeight) > totalPageHeight:
                # whenever only a small part of the screen is left to be screenshot
                yPos = totalPageHeight - viewportHeight
            else:
                # scroll past the previous viewport
                yPos = offset

            self.scrollToPosition(y=yPos)
            time.sleep(0.2)  # Allow page to settle. If not, header sometimes stays at the middle of the page
            offsets.append(yPos)

            img = Image.open(BytesIO(self.selenium.get_screenshot_as_png()))

            offset += img.size[1]

            imageSlices.append(img)

            if not scroll:
                break

        # create an image the size of the full page, or if scroll is false, the size of the first slice
        screenshot = Image.new(
            'RGB',
            (
                imageSlices[0].size[0],
                totalPageHeight if scroll else imageSlices[0].size[1],
            ),
            color=(173, 216, 230),
        )

        # paste the image slices together
        for offsetIndex, img in enumerate(imageSlices):
            screenshot.paste(img, (0, offsets[offsetIndex]))

        self.scrollToPosition()

        return screenshot

    @contextmanager
    def switchToFrame(self, element: OWebElement) -> Generator[None, None, None]:
        self.selenium.switch_to.frame(element._element)  # pylint: disable=protected-access

        yield

        self.selenium.switch_to.default_content()

    @contextmanager
    def switchToTab(self, index: int) -> Generator[None, None, None]:
        windows = self.selenium.window_handles
        if index >= len(windows):
            # Wait for tab to appear
            windows = waitFor(lambda: self.selenium.window_handles, condition=lambda w: len(w) > index)

        self.selenium.switch_to.window(windows[index])

        yield

        self.selenium.switch_to.window(windows[0])
