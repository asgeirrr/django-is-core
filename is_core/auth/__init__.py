from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponseForbidden
from django.template.loader import render_to_string
from django.template.context import RequestContext


class Auth(object):

    def __init__(self, permissions_validators):
        self.permissions_validators = permissions_validators

    def is_authenticated(self, request):
        rm = request.method.upper()

        if not request.user or not request.user.is_active:
            return False

        if not self.permissions_validators.has_key(rm):
            return False

        validators = self.permissions_validators.get(rm)

        if not isinstance(validators, (list, tuple)):
            validators = [validators]

        for validator in validators:
            if validator(request):
                return True
        return False


class AuthWrapper(Auth):

    def __init__(self, permissions_validators):
        super(AuthWrapper, self).__init__(permissions_validators)

    def wrap(self, func):

        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated() and not self.is_authenticated(request):
                return HttpResponseForbidden(render_to_string('403.html', context_instance=RequestContext(request)))

            return login_required(func)(request, *args, **kwargs)

        return wrapper