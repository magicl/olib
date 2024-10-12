# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


# import json
# import logging
# import random
# import re
# import time
# from collections import Counter
# from collections.abc import Callable
# from typing import NamedTuple

# import requests
# import simplejson
# from celery.execute import send_task  # pylint: disable=no-name-in-module,import-error
# from django.conf import settings
# from django.db.models import Case, Value, When
# from django.utils import timezone
# from django.utils.http import urlencode

# from ....models import Asset, AssetTag, HtmlAssetContent
# from ....models.onlinesettings import osettings

# logger = logging.getLogger('manage.sync.plasmic')

# class PalsmicApiException(Exception):
#     def __init__(self, message='', status_code=None, content=None):
#         super().__init__(message)
#         self.message = message
#         self.status_code = status_code
#         self.content = content

#     def __str__(self):
#         return repr(self.message)

# class PlasmicSpec(NamedTuple):
#     pathRegex: str #Used for determining which spec to use. Applied to path in plasmic assets
#     template: str
#     metadata: dict[str, Callable]

# #Prevent upload of project that does not match currently configured project
# shared = {
#     'extractHydrate': lambda c, m: f'pl-{m['projectId']}-{m['id']}',
#     'hydrate':        lambda c, m: m['metadata'].get('hydrate', 'false').lower() != 'false',
#     'globalStyles':   lambda c, m: m['projectId'] if m['metadata'].get('globalStyles', 'false').lower() == 'false' and m['metadata'].get('hydrate', 'false').lower() == 'false' else None, #I.e. 'false' to turn off including global styles in component
#     'reactRoot':      lambda c, m: m['metadata'].get('reactRoot', None),
#     'contentUrl':     lambda c, m: m['pageMetadata'].get('path'),
# }
# onlyMainProject = {
#     'osConditions':   lambda c, m: {'plasmic_currentProjectId': m['projectId']},
# }

# SPECS = [
#     #Main landing-page
#     PlasmicSpec('^/$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: 'Landing Page',
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'lp-...',
#         'template':       lambda c, m: 'plasmic',
#         'noindex':        lambda c, m: True,
#         **shared, **onlyMainProject,
#     }),
#     #Secondary Landing-Pages / Product Landing-Pages
#     PlasmicSpec('^/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'lp-' + m['path'][1:].lower(),
#         'template':       lambda c, m: 'plasmic',
#         'noindex':        lambda c, m: m['metadata'].get('index', 'false').lower() == 'false', #No-index by default, but can enable
#         **shared, **onlyMainProject,
#     }),
#     #PDP Sections
#     PlasmicSpec('^/pdp/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'pdp-' + m['path'][5:].lower(),
#         'template':       lambda c, m: 'plasmic-redirect',
#         'noindex':        lambda c, m: True,
#         **shared, **onlyMainProject,
#     }),
#     #Blog Sections
#     PlasmicSpec('^/blogs/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'blog-' + m['path'][7:].lower(),
#         'template':       lambda c, m: 'plasmic-redirect',
#         'noindex':        lambda c, m: True,
#         **shared, **onlyMainProject,
#     }),
#     #Collection Sections
#     PlasmicSpec('^/collections/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'col-' + m['path'][13:].lower(),
#         'template':       lambda c, m: 'plasmic-redirect',
#         'noindex':        lambda c, m: True,
#         **shared, **onlyMainProject,
#     }),
#     #Register Sections
#     PlasmicSpec('^/register/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'reg-' + m['path'][10:].lower(),
#         'template':       lambda c, m: 'plasmic-redirect',
#         'noindex':        lambda c, m: True,
#         **shared, **onlyMainProject,
#     }),
#     #eCom Cards
#     PlasmicSpec('^/cards/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'crd-' + m['path'][7:].lower(),
#         'template':       lambda c, m: 'plasmic-redirect',
#         'noindex':        lambda c, m: True,
#         **shared, #Cards come from a separate project
#     }),
#     #eCom rows
#     PlasmicSpec('^/rows/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'row-' + m['path'][6:].lower(),
#         'template':       lambda c, m: 'plasmic-redirect',
#         'noindex':        lambda c, m: True,
#         **shared, #Cards come from a separate project
#     }),
#     #Custom Sections
#     PlasmicSpec('^/special/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: 'sp-' + m['path'][9:].lower(),
#         'template':       lambda c, m: 'raw', #Raw enables loading via GET api with no other page overhead.. layout none
#         'noindex':        lambda c, m: True,
#         **shared, **onlyMainProject,
#     }),
#     #Pages
#     PlasmicSpec('^/pages/([^/]+)$', 'tmpl:page-plasmic', {
#         'published':      lambda c, m: True,
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'pageHandle':     lambda c, m: m['path'][7:].lower(),
#         'template':       lambda c, m: 'plasmic' if m['metadata'].get('requireLogin', 'false').lower() == 'false' else 'plasmic-loggedin',
#         'noindex':        lambda c, m: m['metadata'].get('index', 'true').lower() == 'false', #Index pages by default, but can disable in plasmic
#         **shared, **onlyMainProject,
#     }),
#     PlasmicSpec('^/userview/([^/]+)$', 'tmpl:page-plasmic', {
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'doNotUpload':    lambda c, m: True, #Do not push userview pages to shopify
#     }),
#     PlasmicSpec('^/internal/([^/]+)$', 'tmpl:page-plasmic', {
#         'title':          lambda c, m: m['pageMetadata'].get('title') or m['name'],
#         'description':    lambda c, m: m['pageMetadata'].get('description'),
#         'doNotUpload':    lambda c, m: True, #Do not push userview pages to shopify
#     }),
# ]


# class PlasmicApiException(Exception):
#     def __init__(self, message='', status_code=None, content=None):
#         super().__init__(message)
#         self.message = message
#         self.status_code = status_code
#         self.content = content

#     def __str__(self):
#         return repr(self.message)

# class PlasmicSync:
#     def __init__(self, initSession=True, manager=None):
#         self.session = requests.Session() if initSession else None
#         self.floatReg = re.compile('^[+-]?([0-9]*[.])?[0-9]+$')
#         self.intReg = re.compile('^[0-9]+$')

#     def close(self):
#         if self.session is not None:
#             self.session.close()

#     def renderRequest(self, url, preview=False, gql=False, data=None, params=None, ignoreRespData=False, timeout=20):
#         """Requests to JSXServer"""
#         jsxUrl = settings.JSXSERVER_URL
#         params = params or {}
#         fullUrl = f'{jsxUrl}{url}'

#         #logger.debug("{} {}".format(fullUrl, json.dumps(data) if data is not None else ""))

#         tStart = time.time()
#         try:
#             res = self.session.post(fullUrl,
#                                     json=data,
#                                     headers={'content_type': 'application/json'},
#                                     timeout=timeout)
#         except requests.exceptions.ConnectionError as e:
#             logger.exception(f'JSX server not found at {jsxUrl}')
#             raise PlasmicApiException('Unable to connect to JSX-render-server') from e

#         logger.info(f'JSX Server response in {round(time.time() - tStart, 2)} seconds')

#         if res.status_code != 200:
#             logger.error(f'Error response from jsx-server: {res}')
#             raise PlasmicApiException('Error response from JSX-render-server')

#         data = res.json()
#         if data.get('error', False):
#             raise PlasmicApiException('Plasmic error: {}'.format(data['error']))

#         return data

#     def request(self, method, url, plasmicProjectId, data=None, params=None, ignoreRespData=False, throttleLevel=None, throttleTime=0):
#         if settings.MOCK_SERVICES:
#             #Testing can be done in multithreaded enviroment, which is why dynamic calculation is required
#             from tests.runner import getTestThreadId
#             apiUrl = f'http://localhost:{settings.PLASMIC_CODEGEN_API_PORT + getTestThreadId()}'
#         else:
#             apiUrl = settings.PLASMIC_CODEGEN_API_URL

#         params = params or {}
#         fullUrl = f'{apiUrl}{url}?{urlencode(params)}'

#         plasmicProjectToken = osettings.plasmic_projectTokens.get(plasmicProjectId, '')
#         headers = {
#             'x-plasmic-api-project-tokens': f'{plasmicProjectId}:{plasmicProjectToken}',
#             'Content-type': 'application/json',
#         }

#         if method != 'GET' and not settings.PLASMIC_DO_SYNC:
#             logger.warning('Will not perform writeback commands to Bold RO on dev')
#             return None

#         retry = True
#         while retry:
#             retry = False
#             try:
#                 if method == 'GET':
#                     r = self.session.get(fullUrl, json=data, headers=headers)
#                 elif method == 'POST':
#                     r = self.session.post(fullUrl, json=data, headers=headers)
#                 elif method == 'PUT':
#                     r = self.session.put(fullUrl, json=data, headers=headers)
#                 elif method == 'DELETE':
#                     r = self.session.delete(fullUrl, json=data, headers=headers)
#                 elif method == 'PATCH':
#                     r = self.session.patch(fullUrl, json=data, headers=headers)

#                 logger.info(f'plasmic call {method} {fullUrl} response {r.status_code} in {r.elapsed.total_seconds()}')

#             except Exception as e:
#                 msg = f'Invalid response during {method} {fullUrl} - exception: {str(e)}'
#                 logger.error(msg)
#                 raise PlasmicApiException(msg) from e

#             if r.status_code == 429:
#                 #Too many requests. Wait a bit for more to become available
#                 logger.info('hit plasmic call limit')
#                 #Sleep for 0.5-1.5 seconds before retrying
#                 time.sleep(random.uniform(0.5, 3))
#                 retry = True

#             if r.status_code < 200 or r.status_code >= 300:
#                 try:
#                     errJson = r.json()
#                     msg = f'error result {r.status_code} from {method} {fullUrl}\nSENT:{data}\nRECEIVED:{errJson}'
#                     logger.info(f'Plasmic error response: {errJson}')
#                 except (json.JSONDecodeError, simplejson.scanner.JSONDecodeError):
#                     errJson = {}
#                     msg = f'error result {r.status_code} from {method} {fullUrl}\nSENT:{data}\nRECEIVED <unable to parse>:{r.text}'
#                     logger.info(f'Plasmic error response: {r.text}')

#                 raise PlasmicApiException(msg, status_code=r.status_code, content=r.text)

#         if not ignoreRespData:
#             try:
#                 jsonResp = r.json()
#             except Exception as e:
#                 msg = f"Unable to parse\nURL:'{fullUrl}'\nJSON:'{r.text}'\nStatus: {r.status_code}"
#                 logger.error(msg)
#                 raise Exception(msg) from e
#         else:
#             jsonResp = None

#         logger.info(f'plasmic headers: {r.headers}')

#         return jsonResp


#     def _getExpressionValue(self, expr, compName, param, paramVarById, insts=None, refs=None, variables=None, depth=0, debugSchema=False):
#         #Capture. Convert data type
#         _paramName = param['variable']['name']
#         _varId = param['variable']['__iid']
#         _value = None
#         _skip = False
#         _valInfo = None

#         if expr['__type'] == 'CustomCode':
#             _type = param['type']['name']
#             _code = expr['code']

#             #if debugSchema and _paramName == 'collectionHandle':
#             #    breakpoint()
#             #    print('here')

#             if _code in ('undefined', 'null'):
#                 if (_defaultExpr := param['defaultExpr']) is not None:
#                     _code = _defaultExpr['code']
#                 else:
#                     _type = 'null'

#             if _type == 'null':
#                 _value = None
#             elif _type in ('text', 'href', 'choice'):
#                 if _code[0] == '"':
#                     _value = json.loads(_code) #Strip quotes. Also unescapes where necessary
#                 else:
#                     #Currently don't support processing code parameters. Ignore
#                     logger.info(f'Code value for {_paramName} of {compName}: {_code}')
#                     _skip = True

#             elif _type == 'num':
#                 if self.intReg.match(_code):
#                     _value = int(_code)
#                 elif self.floatReg.match(_code):
#                     _value = float(_code)
#                 else:
#                     #Currently don't support processing code parameters. Ignore
#                     logger.info(f'Code value for {_paramName} of {compName}: {_code}')
#                     _skip = True

#             elif _type == 'bool':
#                 if _code == 'true':
#                     _value = True
#                 elif _code == 'false':
#                     _value = False
#                 else:
#                     #Currently don't support processing code parameters. Ignore
#                     logger.info(f'Code value for {_paramName} of {compName}: {_code}')
#                     _skip = True

#             elif _type == 'any':
#                 #Load as JSON
#                 _value = json.loads(_code)
#             elif _type in ('img', 'target'):
#                 #Ignore image/target parameters for now
#                 # * target seems to be used for some booleans. Specifically "open in new tab" for links
#                 _skip = True

#             else:
#                 logger.info(f'Unknown parameter type: {_type} for "{_paramName}" of "{compName}"')
#                 _skip = True

#             if debugSchema:
#                 if _skip:
#                     logger.info(f'Schema: {'  '*depth} {_paramName} SKIP ({_varId})')
#                 else:
#                     logger.info(f'Schema: {'  '*depth} {_paramName} = {_value} ({_varId})')

#         elif expr['__type'] == 'ObjectPath':
#             #Not 100% sure what this is
#             if debugSchema:
#                 logger.info(f'Schema: {'  '*depth} {expr['__type']} = {expr['path']} SKIP')

#         elif expr['__type'] == 'VarRef':
#             #A variable reference
#             varIid = expr['variable']['__iidRef']

#             if varIid in variables:
#                 _, _value = variables[varIid]

#             elif (defaultExpr := param.get('defaultExpr')) is not None:
#                 #No sure if we should look at defaultExpr from param first, or from the referenced paramVar..
#                 #if debugSchema:
#                 #    breakpoint()
#                 _, _value, _, _ = self._getExpressionValue(defaultExpr, compName, param, paramVarById, insts, refs, variables, depth=depth, debugSchema=debugSchema)
#                 _valInfo = 'param.defaultExpr'

#             elif (defaultExpr := paramVarById[varIid][1].get('defaultExpr')) is not None:
#                 #No sure if we should look at defaultExpr from param first, or from the referenced paramVar..
#                 #if debugSchema:
#                 #    breakpoint()
#                 _, _value, _, _ = self._getExpressionValue(defaultExpr, compName, param, paramVarById, insts, refs, variables, depth=depth, debugSchema=debugSchema)
#                 _valInfo = 'paramVar.defaultExpr'

#                 # elif varIid in paramVarById:
#                 #     #No explicit value, but we have a default (?)
#                 #     defParam, defVar = paramVarById[varIid]

#             else:
#                 logger.info(f'Missing variable for {_paramName} of {compName}: __iidRef={varIid}')
#                 #if debugSchema:
#                 #    breakpoint() #do we have it paramVarById??
#                 #print('xx')
#                 _skip = True


#             if debugSchema:
#                 #if _value == 'tea-gifts':
#                 #    breakpoint()
#                 logger.info(f'Schema: {'  '*depth} {expr['__type']}: {_paramName} = {_value}{' ['+_valInfo+']' if _valInfo is not None else ''}')

#         elif expr['__type'] == 'TemplatedString':
#             #List of items that should be combined together
#             _value = ''.join([v if isinstance(v, str) else
#                               str(self._getExpressionValue(v, compName, param, paramVarById, insts, refs, variables, depth=depth, debugSchema=debugSchema)[1])
#                               for v in expr['text']])

#         else:
#             if debugSchema:
#                 logger.info(f'Schema: {'  '*depth} {expr['__type']} SKIP')
#                 logger.info(f'unknown type: {expr}')

#         return _paramName, _value, _varId, _skip


#     def _processSchemaPage(self, tree, compById, paramById, paramVarById, insts=None, refs=None, variables=None, depth=0, debugSchema=False):
#         """
#         Returns a list of component instantiations and associated parameters for page
#         :param tree: tplTree to start with
#         """
#         if insts is None:
#             insts = []
#         if refs is None:
#             refs = Counter()
#         if variables is None:
#             variables = {}


#         objects = tree['children'] if 'children' in tree else [tree]

#         for c in objects:
#             if c['__type'] == 'TplTag':
#                 #Keep digging
#                 self._processSchemaPage(c, compById, paramById, paramVarById, insts, refs, depth=depth+1, debugSchema=debugSchema)

#             elif c['__type'] == 'TplComponent':
#                 if '__uuid' in c['component']:
#                     #This component is from another plasmic project. In the future, we could load those schemas as well, but for now, assume
#                     #there is no need, because we are not instantiating code components in other projects and including back into the main project
#                     #We still want to load sub-items, so continue going
#                     _comp = None
#                     compName = f'Foreign [{c['component']['__uuid']}]'
#                 else:
#                     _comp = compById[c['component']['__iidRef']]
#                     compName = _comp['name']

#                     #Only capture references to local components.. When we have foreign components known, add in them as well..
#                     refs[compName] += 1

#                 # if compName == 'ShopifyProductData' and debugSchema:
#                 #     breakpoint()
#                 #     print('why no args found??')

#                 _args = {}
#                 _variables = variables.copy() if variables is not None else {}

#                 if debugSchema:
#                     logger.info(f'Schema: {'  '*depth}{compName}')

#                 # if c['__iid'] == 8606024:
#                 #     breakpoint()
#                 #     print('wh is productHandle not put in variables list')

#                 #Component. Find arguments
#                 for vsetting in c['vsettings']:
#                     for arg in vsetting['args']:
#                         param = paramById[arg['param']['__iidRef']][0] if _comp is not None else None
#                         expr = arg['expr']

#                         #if param['type']['name'] == 'renderable':
#                         if expr['__type'] == 'RenderExpr':
#                             #E.g. a slot. Traverse
#                             if debugSchema:
#                                 logger.info(f'Schema: {'  '*depth} SLOT')

#                             for tpl in expr['tpl']:
#                                 self._processSchemaPage(tpl, compById, paramById, paramVarById, insts, refs, _variables, depth=depth+1, debugSchema=debugSchema)

#                         elif _comp is not None:
#                             _paramName, _value, _varId, _skip = self._getExpressionValue(expr, compName, param, paramVarById, insts, refs, _variables, depth=depth, debugSchema=debugSchema)

#                             if _paramName is not None and not _skip:
#                                 _args[_paramName] = _value
#                                 #Capture variable. This can be referenced by children
#                                 _variables[_varId] = (_paramName, _value)

#                 if _comp is not None:
#                     #If this is plasmic component, dig in, using current arguments as context
#                     if _comp['type'] == 'plain':
#                         self._processSchemaPage(_comp['tplTree'], compById, paramById, paramVarById, insts, refs, variables=_variables, depth=depth+1, debugSchema=debugSchema)

#                     #Only save args for code components
#                     if _comp['type'] == 'code':
#                         insts.append({'comp': compName, 'args': _args})

#         #'insts' are deep instances.. All code componetns on rendered page that have arguments
#         #'refs' are direct references on this page.. Code and non-code components
#         return insts, refs


#     def readSchema(self, projectId, projectToken, pagesOnly=False):
#         #Load schema for project, and create a reduced representation that we can use, primarily for prepopulating GQL queries for now
#         #https://docs.plasmic.app/learn/model-quickstart/
#         schema = self.request('GET', f'/api/v1/loader/repr-v3/published/{projectId}', projectId)

#         compById = {c['__iid']: c for c in schema['site']['components']} #Components by Id
#         paramById = {p['__iid']: (p, c) for c in schema['site']['components'] for p in c['params']} #Param, Component by param Id
#         paramVarById = {p['variable']['__iid']: (p['variable'], p) for _, (p, _) in paramById.items() if 'variable' in p} #Param, Component by param Id

#         #Go through pages
#         pageMap = {}
#         debugSchema = False
#         debugPage = None #'/collections/iced-tea-header' #Set to page name/url to output for that page. Set to None to disable
#         for _, c in compById.items():
#             if c['pageMeta'] is None:
#                 #Component
#                 if pagesOnly:
#                     continue

#                 name = c['name']
#             else:
#                 #Page
#                 name = c['pageMeta']['path']

#             logger.info(f'Schema: {name}')

#             if debugPage is not None:
#                 debugSchema = name == debugPage
#                 #if debugSchema:
#                 #    breakpoint() #why no top-level variables for component??
#                 #    print('here')
#             # debugSchema = False
#             # if name == '/collections/wellness-tea-shop-header':
#             #     debugSchema = True
#             #     #breakpoint()
#             #     #print('find subcomponents')
#             insts, refs = self._processSchemaPage(c['tplTree'], compById, paramById, paramVarById, depth=1, debugSchema=debugSchema)

#             pageMap[name] = {'insts': insts, 'refs': dict(refs)}

#         #breakpoint()

#         return pageMap


#     @staticmethod
#     def processEvent(call):
#         """Process webhook event from plasmic"""
#         #Could have called syncAssets directly to save time, but do it instead as a separate celery
#         #task to allow proper locking

#         #Embed hook type in data
#         data = json.loads(call.raw_data)
#         projectId = data.get('project')

#         if projectId is None:
#             logger.error('No project specified for plasmic webhook')
#             return

#         send_task('manage.tasks.interactive.syncPlasmicToAssets', kwargs={'projectId': projectId, 'impersonateProjectId': data.get('project')})


#     @staticmethod
#     def getSpecFromPath(path):
#         for spec_ in SPECS:
#             if re.match(spec_.pathRegex, path):
#                 return spec_

#         return None

#     @staticmethod
#     def getMeta(data):
#         return data['entryCompMetas'][0]

#     @staticmethod
#     def getProject(data):
#         projectId = PlasmicSync.getMeta(data)['projectId']
#         for v in data['bundle']['projects']:
#             if v['id'] == projectId:
#                 return v

#         raise Exception('Project data not found in bundle')

#     def syncAssets(self, projectId, impersonateProjectId=None):
#         """Sync"""

#         if impersonateProjectId is None:
#             impersonateProjectId = projectId

#         #Read token for given project
#         projectToken = osettings.plasmic_projectTokens.get(projectId)
#         if projectToken is None:
#             raise Exception(f'No token set for plasmic project {projectId}')

#         plasmicConfig = {
#             'projectId': projectId,
#             'token':     projectToken,
#             'preview':   False,
#         }

#         #Load all pages for given project
#         ret = self.renderRequest('/plasmic/load', data=plasmicConfig, timeout=600)

#         #Load schema for project
#         pageMap = self.readSchema(projectId, projectToken, pagesOnly=True)

#         syncDownstreamAssetIds = []

#         seenKeys = set()
#         for _, p in ret['pageData'].items():
#             #Projects looks like
#             # [{'globalContextsProviderFileName': '',
#             #   'id': 'dRu1Jpq1cwoMtErUYwhXvC',
#             #   'name': 'SaaS Website',
#             #   'remoteFonts': [{'url': '...'}],
#             #   'version': '0.0.1'}]},
#             project = self.getProject(p)

#             #Meta looks like
#             # [{'cssFile': 'css__XBkjlogTqLrGI1.css',
#             #   'displayName': 'Blog',
#             #   'entry': 'render__XBkjlogTqLrGI1.js',
#             #   'id': 'XBkjlogTqLrGI1',
#             #   'isCode': False,
#             #   'isPage': True,
#             #   'metadata': {},
#             #   'name': 'Blog',
#             #   'pageMetadata': {'description': '', 'path': '/blog', 'title': None},
#             #   'path': '/blog',
#             #   'projectId': 'dRu1Jpq1cwoMtErUYwhXvC',
#             #   'renderFile': 'render__XBkjlogTqLrGI1.js',
#             #   'skeletonFile': 'comp__XBkjlogTqLrGI1.js',
#             #   'usedComponents': ['a39iVHgDih59WB', '0pkYGNKyddrwk', 'OjZn7_H-TXFEag']}]
#             meta    = self.getMeta(p)

#             key  = f'{Asset.Prefixes.PlasmicPage.value}{impersonateProjectId}-{meta['id']}'
#             seenKeys.add(key)

#             name = project['version']

#             #Find the right spec. Spec is found based on path match
#             path = meta['path']
#             spec = PlasmicSync.getSpecFromPath(path)
#             title = meta['pageMetadata'].get('title') or meta['name']

#             if spec is None:
#                 logger.error(f'Invalid Entry Path: {path}')
#                 continue

#             #Add schema data to page
#             pageSchema = pageMap.get(path)
#             if pageSchema is None:
#                 logger.error(f'page schema not found for {path}')
#                 #Keep going in this case for test cases

#             if 'schema' in p:
#                 raise Exception('"schema" already in output from plasmic. We need to rename our schema field')
#             p['schema'] = pageSchema
#             #breakpoint() #no inst args in schema?/

#             #Plasmic assets are always published (for now)
#             visible = True
#             content = json.dumps(p, indent=2)

#             #Get current if available
#             hac = HtmlAssetContent.objects.select_related('asset').filter(asset__key=key, name=name, deleted=False, asset__active=True).first()
#             updated = False

#             if hac is None:
#                 #No hac. Do we have an asset?
#                 asset = Asset.objects.filter(key=key, active=True).first()

#                 #Create version
#                 logger.info(f'plasmic - create: {title} ({name})')
#                 hac = HtmlAssetContent.create(spec.template, asset=hac.asset if hac is not None else asset, key=key, version=name, content=content,
#                                               managed=True, selected=True, metaUpdate=False, visible=visible)
#                 updated = True

#             else:
#                 #Update asset content if it changed
#                 if (hac.base_template_name != spec.template or
#                     hac.html_content != content or
#                     hac.asset.visible != visible):

#                     logger.info(f'plasmic - update: {title} ({name})')
#                     hac.base_template_name = spec.template
#                     hac.html_content = content
#                     hac.updated_at = timezone.now()
#                     hac.visible = True
#                     hac.selected = True
#                     hac.save()

#                     updated = True
#                 else:
#                     logger.info(f'plasmic - no-chg: {title} ({name})')

#             #Add plasmic path as asset tag, as we'll use this for e.g. mapping plasmic assets to userviews
#             if AssetTag.ensureTags(hac.asset_id, [(AssetTag.TagType.IURL, path), (AssetTag.TagType.SOURCE, projectId)]) > 0:
#                 updated = True

#             #Inline update to ensure it is ready for pickup by syncAssetsToShopify if a publish comes right after
#             if hac.updateMetadata()[1]:
#                 updated = True

#             #Asset is ready. Update selected-state
#             HtmlAssetContent.objects.filter(asset_id=hac.asset.id).update(selected=Case(When(id=hac.id, then=Value(True)), default=Value(False)))

#             if updated:
#                 syncDownstreamAssetIds.append(hac.asset.id)

#         #Find any assets that are no longer in the project and mark them as deleted so they can be unpublished
#         #Only unpublish from the project that is currently being synced
#         missingAssetIds = list(Asset.objects.filter(key__startswith=Asset.Prefixes.PlasmicPage.value, active=True)
#                                .exclude(key__in=seenKeys)
#                                .filter(assettag__tagtype = AssetTag.TagType.SOURCE.value, assettag__tagvalue = projectId, assettag__active=True)
#                                .values_list('id', flat=True))
#         if missingAssetIds:
#             Asset.objects.filter(id__in=missingAssetIds).update(active=False)
#             syncDownstreamAssetIds += missingAssetIds

#         if syncDownstreamAssetIds and osettings.plasmic_shopifyUpdateEnabled:
#             #Ensure assets are pushed to shopify
#             send_task('manage.tasks.interactive.syncAssetsToShopify', kwargs={'assetIds': syncDownstreamAssetIds})


#     def createUsageReport(self, projectId):
#         projectToken = osettings.plasmic_projectTokens[projectId]

#         #Load schema for project
#         pageMap = self.readSchema(projectId, projectToken)

#         usageMap = {name: {'useCount': 0, 'usedIn': set()} for name, _ in pageMap.items()}
#         for name, data in pageMap.items():
#             for ref in data['refs']:
#                 #Still need this in case of external refs
#                 if ref not in usageMap:
#                     usageMap[ref] = {'useCount': 0, 'usedIn': set()}

#                 comp = usageMap[ref]
#                 comp['useCount'] += 1
#                 comp['usedIn'].add(name)

#         #Clean up and return
#         for _, comp in usageMap.items():
#             comp['usedIn'] = list(comp['usedIn'])

#         #Sort by key
#         return dict(sorted(usageMap.items(), key=lambda v: v[0]))
