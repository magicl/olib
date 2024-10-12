# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~
import atexit
import datetime
import logging
import os
import shutil
import tempfile
import uuid
from typing import Any

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager

logger = logging.getLogger(__name__)


class BrowserNames:
    CHROME = 'chrome'
    FIREFOX = 'firefox'
    ALL = [CHROME, FIREFOX]


def _getBlockUrls(blockUrls):
    # Block trackers
    return [
        '*googleadservices.*',
        '*klaviyo.*',
        '*lightwidget.*',
        '*shareasale.*',
        '*dwin1.*',
        '*googleads.*',
        '*pinimg.*',
        '*pinterest.*',
        '*google-analytics.*',
        '*facebook.*',
        '*analytics.*',
        '*doubleclick.*',
        '*instagram.*',
        '*apis.google.com.*',
    ]


class DriverWrapper:
    def __init__(self, driver, downloadDir):
        self.driver = driver
        self.downloadDir = downloadDir
        self.useCount = 0

    @property
    def name(self):
        return self.driver.name


class Chrome(DriverWrapper):
    DEFAULT: list[str] = [
        'fast',
        'verbose',
        'disable-gpu',
        'disable-browser-side-navigation',
        'disable-dev-shm-usage',
        'no-sandbox',
        'disable-preconnect',
    ]

    def __init__(self, driver, downloadDir, tmpDir):
        self._tmpDir = tmpDir
        super().__init__(driver, downloadDir)

    def quit(self):
        self.driver.quit()
        if self._tmpDir is not None:
            shutil.rmtree(self._tmpDir)

    @classmethod
    def options(cls, downloadDir, **kwargs):
        options = webdriver.ChromeOptions()
        tmpDir = None

        for opt in cls.DEFAULT:
            options.add_argument(opt)

        if not kwargs.get('gui', False):
            options.add_argument('--headless=new')  # Comment out this line to open a GUI
            # By default, in headless mode, useragent is set to e.g. 'headless chrome', making bold checkout fail.. Fake a
            # better user-agent
            options.add_argument(
                'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'
            )

        # Switches: https://peter.sh/experiments/chromium-command-line-switches/
        if kwargs.get('devtools', False):
            # automatically open dev-tools in Chrome
            options.add_argument('auto-open-devtools-for-tabs')
        if kwargs.get('maximized', False):
            options.add_argument('start-maximized')

        if kwargs.get('userProfile', False):
            # We want to run selenium in the same context as a regular user session to have access
            # to passwords, etc. to make accessing services easier. Copy the current user profile
            # to prevent issues with overwriting data in it
            profileDir = os.path.expanduser('~/.config/google-chrome')
            tmpDir = tempfile.mkdtemp(prefix='selenium-userprofile-')
            shutil.copytree(profileDir, tmpDir, dirs_exist_ok=True, symlinks=True)

            options.add_argument(f"user-data-dir={tmpDir}")

            print('delete tmpDir on exit')

        # Set download directory
        options.add_experimental_option(
            'prefs',
            {
                'profile.default_content_settings.popups': 0,
                'download.default_directory': downloadDir or '/tmp/',  # nosec: Download dir
            },
        )

        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        return options, tmpDir

    @classmethod
    def createDriver(cls, downloadDir=None, blockUrls=False, proxy=None, **kwargs):
        from selenium.webdriver.chrome.service import Service as ChromeService

        options, tmpDir = cls.options(downloadDir, **kwargs)
        # service = ChromeService(executable_path='/usr/local/bin/chromedriver')
        try:
            executablePath = ChromeDriverManager().install()
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Unable to connect to the internet / check for new driver / download new driver. Use one from the cache.
            # No support for this in library, so do it manually
            # Cache format:
            #  {'linux64_chromedriver_114.0.5735.90_for_114.0.5735': {
            #    'binary_path': '/home/vagrant/.wdm/drivers/chromedriver/linux64/114.0.5735.90/chromedriver',
            #    'timestamp': '27/10/2023'}}
            cache = DriverCacheManager().load_metadata_content()
            if not cache:
                raise Exception('Not able to download web driver, and none in cache') from e

            cacheItems = sorted(
                [{'key': k, **v} for k, v in cache],
                key=lambda v: datetime.datetime.strptime(v['timestamp'], '%m/%d/%y'),
                reverse=True,
            )
            version = cacheItems[0]['binary_path'].rsplit()[-2]

            executablePath = ChromeDriverManager(driver_version=version).install()

        driver = webdriver.Chrome(service=ChromeService(executablePath), options=options)

        if not kwargs.get('noUrlBlock'):
            driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': _getBlockUrls(blockUrls)})
            driver.execute_cdp_cmd('Network.enable', {})

        return Chrome(driver, downloadDir, tmpDir)


class Firefox(DriverWrapper):
    DEFAULT: list[str] = []

    @classmethod
    def options(cls):
        options = webdriver.FirefoxOptions()
        for opt in cls.DEFAULT:
            options.add_argument(opt)
        # Disabling this option can result in an error when initializing the firefox webdriver "Can't exit an already exited process"
        # if not settings.TEST_SELENIUM_GUI:
        #    options.headless = True
        return options

    @classmethod
    def profile(cls, downloadDir=None):
        profile = webdriver.FirefoxProfile()
        profile.set_preference('browser.download.folderList', 2)  # custom location
        profile.set_preference('browser.download.manager.showWhenStarting', False)
        profile.set_preference('browser.download.dir', downloadDir or '/tmp')  # nosec: download dir
        profile.set_preference('browser.helperApps.neverAsk.saveToDisk', 'text/csv')
        return profile

    @classmethod
    def desiredCapabilities(cls):
        desiredCapabilities = DesiredCapabilities.FIREFOX
        return desiredCapabilities

    @classmethod
    def createDriver(cls, downloadDir=None, blockUrls=False, proxy=None):
        raise Exception('need to get firefox running again')


class SeleniumBrowser:
    """
    Manages selenium webdrivers for all browsers.
    """

    drivers: dict[tuple[str, bool], Any] = {}

    MAX_DRIVER_USE_COUNT = 20

    # modified from https://stackoverflow.com/a/524715
    preparePageForScreenshotScript = """
        const styleNode = document.createElement("style");
        const cssText = `
            *, *::before, *::after { /* make animations complete in 1ms */
                -moz-transition: all 1ms !important;
                transition: all 1ms !important;
                -moz-animation: 1ms !important;
                animation: 1ms !important;
                animation-duration: 1ms !important;
                animation-delay: 0 !important;
                // this might not handle infinite animations.
                animation-iteration-count: 1 !important;
            }
            input { /* stops cursor/caret flashing from causing false positives */
                caret-color: transparent !important;
            }

            /* visually hide scrollbars */
            body {
                scrollbar-width: none; /* firefox */
                -ms-overflow-style: none; /* IE 10+ */
            }
            body::-webkit-scrollbar { /* WebKit */
                width: 0;
                height: 0;
            }
            * { /* makes scrolling instantaneous for full page screenshots */
                scroll-behavior: auto !important;
            }
        `;

        // add styles to document with support for different browsers
        if (!!(window.attachEvent && !window.operate)) {
            styleNode.styleSheet.cssText = cssText;
        } else {
            var styleText = document.createTextNode(cssText);
            styleNode.appendChild(styleText);
        }
        document.getElementsByTagName("head")[0].appendChild(styleNode);

        // prevents fixed headers from repeating in snapshots
        const moddedElements = Array.from(document.body.getElementsByTagName("*")).filter(el => getComputedStyle(el).getPropertyValue('position') === 'fixed').map(el => {
            const prevPosition = el.style.position;
            el.style.position = 'absolute';
            return [el, prevPosition]
        });

        // adds a function to the window that removes all of the above modifications when called
        window._olib_undoScreenshotModifications = () => {
            styleNode.remove();
            moddedElements.forEach(([el, prevPosition]) => el.style.position = prevPosition);
            window._olib_undoScreenshotModifications = null;
        }
    """

    @classmethod
    def _createDriver(cls, browserName, downloadDir, blockUrls=False, **kwargs):
        """
        Instantiates a new webdriver by browserName
        """
        if browserName == BrowserNames.CHROME:
            driver = Chrome.createDriver(downloadDir, blockUrls, **kwargs)
        elif browserName == BrowserNames.FIREFOX:
            driver = Firefox.createDriver(downloadDir, **kwargs)
        else:
            raise Exception(f"Unknown browser type: {browserName}")

        cls.drivers[(driver.name, blockUrls)] = driver

        return driver

    @classmethod
    def getBrowser(cls, browserName, blockUrls, **kwargs):
        """
        :return: A selenium webdriver that matches browserName
        """
        driverKey = (browserName, blockUrls)

        if (driver := cls.drivers.get(driverKey)) is not None:
            driver.useCount += 1
            return driver.driver, driver.downloadDir

        # New download dir for each invocation to be able to easily find any downloaded files
        downloadDir = f"/tmp/{uuid.uuid4()}/"  # nosec: download dir
        os.mkdir(downloadDir)

        newDriver = cls._createDriver(browserName, downloadDir, blockUrls, **kwargs)
        return newDriver.driver, newDriver.downloadDir

    @classmethod
    def quit(cls):
        for driver in cls.drivers.values():
            driver.quit()
        cls.drivers = {}

    @classmethod
    def preparePageForScreenshot(cls, driver):
        """
        Animations and caret flashing can cause false positives in our visual snapshot testing.
        Scrollbars make the resulting snapshots noisy.
        This method injects styles that fix these problems.
        """
        driver.execute_script(cls.preparePageForScreenshotScript)

    @classmethod
    def undoPreparePageForScreenshot(cls, driver):
        driver.execute_script(
            'if (window._olib_undoScreenshotModifications) window._olib_undoScreenshotModifications()'
        )


# Try our best to quit all selenium browsers when the program exits
atexit.register(SeleniumBrowser.quit)
