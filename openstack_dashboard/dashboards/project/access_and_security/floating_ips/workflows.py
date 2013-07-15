
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 Nebula, Inc.

#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import workflows

from openstack_dashboard import api
from openstack_dashboard.utils.filters import get_int_or_uuid


ALLOCATE_URL = "horizon:project:access_and_security:floating_ips:allocate"


class AssociateIPAction(workflows.Action):
    ip_id = forms.DynamicTypedChoiceField(label=_("IP Address"),
                                          coerce=get_int_or_uuid,
                                          empty_value=None,
                                          add_item_link=ALLOCATE_URL)
    instance_id = forms.ChoiceField(label=_("Instance"))

    class Meta:
        name = _("IP Address")
        help_text = _("Select the IP address you wish to associate with "
                      "the selected instance.")

    def __init__(self, *args, **kwargs):
        super(AssociateIPAction, self).__init__(*args, **kwargs)
        if api.base.is_service_enabled(self.request, 'network'):
            label = _("Port to be associated")
        else:
            label = _("Instance to be associated")
        self.fields['instance_id'].label = label

        # If AssociateIP is invoked from instance menu, instance_id parameter
        # is passed in URL. In Neutron based Floating IP implementation
        # an association target is not an instance but a port, so we need
        # to get an association target based on a received instance_id
        # and set the initial value of instance_id ChoiceField.
        q_instance_id = self.request.GET.get('instance_id')
        if q_instance_id:
            target_id = api.network.floating_ip_target_get_by_instance(
                self.request, q_instance_id)
            self.initial['instance_id'] = target_id

    def populate_ip_id_choices(self, request, context):
        try:
            ips = api.network.tenant_floating_ip_list(self.request)
        except:
            redirect = reverse('horizon:project:access_and_security:index')
            exceptions.handle(self.request,
                              _('Unable to retrieve floating IP addresses.'),
                              redirect=redirect)
        options = sorted([(ip.id, ip.ip) for ip in ips if not ip.port_id])
        if options:
            options.insert(0, ("", _("Select an IP address")))
        else:
            options = [("", _("No IP addresses available"))]

        return options

    def populate_instance_id_choices(self, request, context):
        try:
            targets = api.network.floating_ip_target_list(self.request)
        except:
            redirect = reverse('horizon:project:access_and_security:index')
            exceptions.handle(self.request,
                              _('Unable to retrieve instance list.'),
                              redirect=redirect)
        instances = []
        for target in targets:
            instances.append((target.id, target.name))

        # Sort instances for easy browsing
        instances = sorted(instances, key=lambda x: x[1])

        neutron_enabled = api.base.is_service_enabled(request, 'network')
        if instances:
            if neutron_enabled:
                label = _("Select a port")
            else:
                label = _("Select an instance")
            instances.insert(0, ("", label))
        else:
            if neutron_enabled:
                label = _("No ports available")
            else:
                label = _("No instances available")
            instances = (("", label),)
        return instances


class AssociateIP(workflows.Step):
    action_class = AssociateIPAction
    contributes = ("ip_id", "instance_id", "ip_address")

    def contribute(self, data, context):
        context = super(AssociateIP, self).contribute(data, context)
        ip_id = data.get('ip_id', None)
        if ip_id:
            ip_choices = dict(self.action.fields['ip_id'].choices)
            context["ip_address"] = ip_choices.get(ip_id, None)
        return context


class IPAssociationWorkflow(workflows.Workflow):
    slug = "ip_association"
    name = _("Manage Floating IP Associations")
    finalize_button_name = _("Associate")
    success_message = _('IP address %s associated.')
    failure_message = _('Unable to associate IP address %s.')
    success_url = "horizon:project:access_and_security:index"
    default_steps = (AssociateIP,)

    def format_status_message(self, message):
        return message % self.context.get('ip_address', 'unknown IP address')

    def handle(self, request, data):
        try:
            api.network.floating_ip_associate(request,
                                              data['ip_id'],
                                              data['instance_id'])
        except:
            exceptions.handle(request)
            return False
        return True
