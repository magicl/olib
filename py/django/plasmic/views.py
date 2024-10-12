# Licensed under the Apache License, Version 2.0 (the "License");
# Copyright 2024 Øivind Loe
# See LICENSE file or http://www.apache.org/licenses/LICENSE-2.0 for details.
# ~


# import logging

# from django.conf import settings
# from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
# from django.shortcuts import render
# from django.views.decorators.clickjacking import xframe_options_exempt
# from django.views.decorators.csrf import csrf_exempt

# from manage.tasks import processWebhookTask
# from shopify.models import WebHookCall
# from ..models.onlinesettings import osettings

# logger = logging.getLogger(__name__)


# #Handle webhook. Calls external function if available
# #Expects:
# #  POST
# #  header: WEBHOOK-SECRET
# #  payload: {
# #    "project": "<project-id>",
# #    "impersonate": "<project-id-to-impersonate>" (optional)
# #  }

# @csrf_exempt
# def plasmicWebhook(request):
#     logger.debug('plasmic webhook try')
#     logger.debug(request.META)

#     # Try to get required headers and decode the body of the request.
#     try:
#         webhook_secret    = request.headers['webhook-secret']
#         webhook_body      = request.body.decode('utf-8')
#         webhookName       = 'publish'
#         targetId          = 0
#     except Exception as e:
#         logger.exception(f'plasmic webhook decode error: {e}')
#         return HttpResponseBadRequest()

#     # Verify the HMAC.
#     if webhook_secret != settings.PLASMIC_WEBHOOK_SECRET:
#         logger.exception(f'plasmic webhook {webhookName} auth error')
#         return HttpResponseForbidden()


#     #Save call before processing
#     call = WebHookCall.objects.create(hook_name=f'plasmic-{webhookName}',
#                                       raw_data=webhook_body,
#                                       headers=str(request.META),
#                                       http_status=200,
#                                       state=WebHookCall.State.RECEIVED.value,
#                                       target_id = targetId)

#     logger.debug(f'plasmic webhook ({call.id}) {webhookName} saved')

#     #Deferred execution
#     processWebhookTask.apply_async((call.id, ))

#     resp = HttpResponse()
#     resp.status_code = 200
#     return resp

# @xframe_options_exempt #This is needed because plasmic is loading us in an iframe
# @csrf_exempt
# def plasmicHost(request):
#     """Renders an App Host which Plasmic.app uses to learn about and render custom comopnents"""

#     componentsProjectId = request.GET.get('projectId')
#     if componentsProjectId is None:
#         raise Exception('projectId missing in query string')

#     projectToken        = osettings.plasmic_projectTokens.get(componentsProjectId)
#     if projectToken is None:
#         raise Exception('projectToken for componentProjectId missing in osettings plasmic_projectTokens')

#     context = {
#         'componentsProjectId': componentsProjectId,
#         'projectToken': projectToken,
#         '..._domain': settings.CALLBACK_HOST,
#     }

#     return render(request, 'shopify/plasmic_apphost.html', context, using='jinja2')
