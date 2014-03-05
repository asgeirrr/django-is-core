from django.http.response import HttpResponse
from django.template.defaultfilters import lower
from django.db.models.fields.related import RelatedField

from piston.utils import MimerDataException, Mimer as PistonMimer
from piston.handler import typemapper, handler_tracker


# Because django-piston bug
class rc_factory(object):
    """
    Status codes.
    """
    CODES = dict(ALL_OK=({'success': 'OK'}, 200),
                 CREATED=({'success': 'The record was created'}, 201),
                 DELETED=('', 204),  # 204 says "Don't send a body!"
                 BAD_REQUEST=({'error': 'Bad Request'}, 400),
                 FORBIDDEN=({'error':'Forbidden'}, 401),
                 NOT_FOUND=({'error':'Not Found'}, 404),
                 DUPLICATE_ENTRY=({'error': 'Conflict/Duplicate'}, 409),
                 NOT_HERE=({'error': 'Gone'}, 410),
                 UNSUPPORTED_MEDIA_TYPE=({'error': 'Unsupported Media Type'}, 415),
                 INTERNAL_ERROR=({'error': 'Internal server error'}, 500),
                 NOT_IMPLEMENTED=({'error': 'Not implemented'}, 501),
                 THROTTLED=({'error': 'The resource was throttled'}, 503))

    def __getattr__(self, attr):
        """
        Returns a fresh `HttpResponse` when getting
        an "attribute". This is backwards compatible
        with 0.2, which is important.
        """
        try:
            (r, c) = self.CODES.get(attr)
        except TypeError:
            raise AttributeError(attr)

        class HttpResponseWrapper(HttpResponse):
            """
            Wrap HttpResponse and make sure that the internal_base_content_is_iter 
            flag is updated when the _set_content method (via the content
            property) is called
            """
            def _set_content(self, content):
                """
                type of the value parameter. This logic is in the construtor
                for HttpResponse, but doesn't get repeated when setting
                HttpResponse.content although this bug report (feature request)
                suggests that it should: http://code.djangoproject.com/ticket/9403
                """
                if not isinstance(content, basestring) and hasattr(content, '__iter__'):
                    self._container = {'messages': content}
                    self._base_content_is_iter = False
                else:
                    self._container = [content]
                    self._base_content_is_iter = True

            content = property(HttpResponse.content.getter, _set_content)

        return HttpResponseWrapper(r, content_type='text/plain', status=c)

rc = rc_factory()


class UnsupportedMediaTypeException(Exception):
    pass


class Mimer(PistonMimer):

    def translate(self):
        """
        Will look at the `Content-type` sent by the client, and maybe
        deserialize the contents into the format they sent. This will
        work for JSON, YAML, XML and Pickle. Since the data is not just
        key-value (and maybe just a list), the data will be placed on
        `request.data` instead, and the handler will have to read from
        there.
        
        It will also set `request.content_type` so the handler has an easy
        way to tell what's going on. `request.content_type` will always be
        None for form-encoded and/or multipart form data (what your browser sends.)
        """
        ctype = self.content_type()
        self.request.content_type = ctype

        if not self.is_multipart() and ctype:
            loadee = self.loader_for_type(ctype)
            if loadee:
                try:
                    self.request.data = loadee(self.request.body)

                    # Reset both POST and PUT from request, as its
                    # misleading having their presence around.
                    self.request.POST = self.request.PUT = dict()
                except (TypeError, ValueError):
                    # This also catches if loadee is None.
                    raise MimerDataException
            else:
                raise UnsupportedMediaTypeException

        return self.request


def translate_mime(request):
    request = Mimer(request).translate()


def model_handlers_to_dict():
    model_handlers = {}
    for handler in handler_tracker:
        if hasattr(handler, 'model'):
            model = handler.model
            label = lower('%s.%s' % (model._meta.app_label, model._meta.object_name))
            model_handlers[label] = handler
    return model_handlers


def model_default_rest_fields(model):
    rest_fields = []
    for field in model._meta.fields:
        if isinstance(field, RelatedField):
            rest_fields.append((field.name, ('id', '_obj_name', '_rest_links')))
        else:
            rest_fields.append(field.name)
    return rest_fields


def list_to_dict(list_obj):
    dict_obj = {}
    for val in list_obj:
        if isinstance(val, (list, tuple)):
            dict_obj[val[0]] = list_to_dict(val[1])
        else:
            dict_obj[val] = {}
    return dict_obj


def dict_to_list(dict_obj):
    list_obj = []
    for key, val in dict_obj.items():
        if val:
            list_obj.append((key, dict_to_list(val)))
        else:
            list_obj.append(key)
    return tuple(list_obj)


def join_dicts(dict_obj1, dict_obj2):
    joined_dict = dict_obj1.copy()

    for key2, val2 in dict_obj2.items():
        val1 = joined_dict.get(key2)
        if not val1:
            joined_dict[key2] = val2
        elif not val2:
            continue
        else:
            joined_dict[key2] = join_dicts(val1, val2)
    return joined_dict


def flat_list(list_obj):
    flat_list_obj = []
    for val in list_obj:
        if isinstance(val, (list, tuple)):
            flat_list_obj.append(val[0])
        else:
            flat_list_obj.append(val)
    return flat_list_obj


class RestOptions(object):
    def __init__(self, model):
        self.fields = model_default_rest_fields(model)
        self.default_list_fields = self.fields
        self.default_obj_fields = self.fields
        self.selectbox_fields = ('id', '_obj_name')
        self.image_field = None

        if hasattr(model, 'RestMeta'):
            self.fields = getattr(model.RestMeta, 'fields', self.fields)
            self.default_list_fields = getattr(model.RestMeta, 'default_list_fields' , self.default_list_fields)
            self.default_obj_fields = getattr(model.RestMeta, 'default_obj_fields', self.default_obj_fields)
            self.image_field = getattr(model.RestMeta, 'image_field', self.image_field)
            self.selectbox_fields = getattr(model.RestMeta, 'selectbox_fields', self.selectbox_fields)

        self.fields = set(self.fields)
        self.default_list_fields = set(self.default_list_fields)
        self.default_obj_fields = set(self.default_obj_fields)
        self.selectbox_fields = list(self.selectbox_fields)
        if self.image_field:
            self.selectbox_fields.append(self.image_field)


def set_model_rest_meta(model):
    model._rest_meta = RestOptions(model)
