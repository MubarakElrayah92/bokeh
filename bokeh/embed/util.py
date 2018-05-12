#-----------------------------------------------------------------------------
# Copyright (c) 2012 - 2017, Anaconda, Inc. All rights reserved.
#
# Powered by the Bokeh Development Team.
#
# The full license is in the file LICENSE.txt, distributed with this software.
#-----------------------------------------------------------------------------
'''

'''

#-----------------------------------------------------------------------------
# Boilerplate
#-----------------------------------------------------------------------------
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
log = logging.getLogger(__name__)

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

# Standard library imports
from collections import Sequence, OrderedDict

# External imports
from six import string_types

# Bokeh imports
from ..core.json_encoder import serialize_json
from ..core.templates import _env, DOC_JS, FILE, MACROS, PLOT_DIV, SCRIPT_TAG
from ..document.document import DEFAULT_TITLE, Document
from ..model import Model, collect_models
from ..settings import settings
from ..util.compiler import bundle_all_models
from ..util.serialization import make_id
from ..util.string import encode_utf8, indent

#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# General API
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# Dev API
#-----------------------------------------------------------------------------

class FromCurdoc(object):
    ''' This class merely provides a non-None default value for ``theme``
    arguments, since ``None`` itself is a meaningful value for users to pass.

    '''
    pass

def check_models_or_docs(models, allow_dict=False):
    '''

    '''
    input_type_valid = False

    # Check for single item
    if isinstance(models, (Model, Document)):
        models = [models]

    # Check for sequence
    if isinstance(models, Sequence) and all(isinstance(x, (Model, Document)) for x in models):
        input_type_valid = True

    if allow_dict:
        if isinstance(models, dict) and \
           all(isinstance(x, string_types) for x in models.keys()) and \
           all(isinstance(x, (Model, Document)) for x in models.values()):
            input_type_valid = True

    if not input_type_valid:
        if allow_dict:
            raise ValueError(
                'Input must be a Model, a Document, a Sequence of Models and Document, or a dictionary from string to Model and Document'
            )
        else:
            raise ValueError('Input must be a Model, a Document, or a Sequence of Models and Document')

    return models

def check_one_model_or_doc(model):
    '''

    '''
    models = check_models_or_docs(model)
    if len(models) != 1:
        raise ValueError("Input must be exactly one Model or Document")
    return models[0]

def submodel_has_python_callbacks(models):
    ''' Traverses submodels to check for Python (event) callbacks

    '''
    has_python_callback = False
    for model in collect_models(models):
        if len(model._callbacks) > 0 or len(model._event_callbacks) > 0:
            has_python_callback = True
            break

    return has_python_callback

def div_for_render_item(item):
    '''

    '''
    return PLOT_DIV.render(elementid=item['elementid'])

def find_existing_docs(models):
    '''

    '''
    existing_docs = set(m if isinstance(m, Document) else m.document for m in models)
    existing_docs.discard(None)

    if len(existing_docs) == 0:
        # no existing docs, use the current doc
        doc = Document()
    elif len(existing_docs) == 1:
        # all existing docs are the same, use that one
        doc = existing_docs.pop()
    else:
        # conflicting/multiple docs, raise an error
        msg = ('Multiple items in models contain documents or are '
               'themselves documents. (Models must be owned by only a '
               'single document). This may indicate a usage error.')
        raise RuntimeError(msg)
    return doc

def html_page_for_render_items(bundle, docs_json, render_items, title,
                               template=None, template_variables={}):
    '''

    '''
    if title is None:
        title = DEFAULT_TITLE

    bokeh_js, bokeh_css = bundle

    json_id = make_id()
    json = escape(serialize_json(docs_json), quote=False)
    json = wrap_in_script_tag(json, "application/json", json_id)

    script = bundle_all_models()
    script += script_for_render_items(json_id, render_items)
    script = wrap_in_script_tag(script)

    context = template_variables.copy()

    context.update(dict(
        title = title,
        bokeh_js = bokeh_js,
        bokeh_css = bokeh_css,
        plot_script = json + script,
        docs = [
            dict(
                elementid=item["elementid"],
                roots=[ dict(elementid=elementid) for elementid in item['roots'].values() ],
            ) for item in render_items
        ],
        base = FILE,
        macros = MACROS,
    ))

    if len(render_items) == 1:
        context["doc"] = context["docs"][0]

    if template is None:
        template = FILE
    elif isinstance(template, string_types):
        template = _env.from_string("{% extends base %}\n" + template)

    html = template.render(context)
    return encode_utf8(html)

def script_for_render_items(docs_json_or_id, render_items, app_path=None, absolute_url=None):
    '''

    '''
    if isinstance(docs_json_or_id, string_types):
        docs_json = "document.getElementById('%s').textContent" % docs_json_or_id
    else:
        # XXX: encodes &, <, > and ', but not ". This is because " is used a lot in JSON,
        # and encoding it would significantly increase size of generated files. Doing so
        # is safe, because " in strings was already encoded by JSON, and the semi-encoded
        # JSON string is included in JavaScript in single quotes.
        docs_json = serialize_json(docs_json_or_id, pretty=False) # JSON string
        docs_json = escape(docs_json, quote=("'",))               # make HTML-safe
        docs_json = docs_json.replace("\\", "\\\\")               # double encode escapes
        docs_json =  "'" + docs_json + "'"                        # JS string

    js = DOC_JS.render(
        docs_json=docs_json,
        render_items=serialize_json(render_items, pretty=False),
        app_path=app_path,
        absolute_url=absolute_url,
    )

    if not settings.dev:
        js = wrap_in_safely(js)

    return wrap_in_onload(js)

def standalone_docs_json_and_render_items(models):
    '''

    '''
    models = check_models_or_docs(models)
    if submodel_has_python_callbacks(models):
        msg = ('You are generating standalone HTML/JS output, but trying to '
               'use real Python callbacks (i.e. with on_change or on_event). '
               'This cannot work. Only JavaScript callbacks may be used '
               'with standalone output. For more information on JavaScript '
               'callbacks, see\n\n'
               'http://bokeh.pydata.org/en/latest/docs/user_guide/interaction/callbacks.html#userguide-interaction-jscallbacks\n\n'
                'Alternatively, to use real Python callbacks, a Bokeh server '
               'application may be used. For more information on building and '
               'running Bokeh applications, see\n\n'
               ' http://bokeh.pydata.org/en/latest/docs/user_guide/server.html')
        log.warn(msg)


    render_items = []
    docs_by_id = {}
    for p in models:
        modelid = None
        if isinstance(p, Document):
            doc = p
        else:
            if p.document is None:
                raise ValueError("to render a model as HTML it must be part of a document")
            doc = p.document
            modelid = p._id
        docid = None
        for key in docs_by_id:
            if docs_by_id[key] == doc:
                docid = key
        if docid is None:
            docid = make_id()
            docs_by_id[docid] = doc

        elementid = make_id()

        render_item = dict(
            docid = docid,
            elementid = elementid,
            # if modelid is None, that means the entire document
        )

        if modelid is None:
            render_item["modelid"] = None
            render_item["roots"] = OrderedDict([ (root._id, make_id()) for root in doc.roots ])
        else:
            render_item["modelid"] = modelid
            render_item["roots"] = OrderedDict([ (modelid, elementid) ])

        render_items.append(render_item)

    docs_json = {}
    for k, v in docs_by_id.items():
        docs_json[k] = v.to_json()

    return (docs_json, render_items)

def wrap_in_onload(code):
    '''

    '''
    return _ONLOAD % dict(code=indent(code, 4))

def wrap_in_safely(code):
    '''

    '''
    return _SAFELY % dict(code=indent(code, 2))

def wrap_in_script_tag(js, type="text/javascript", id=None):
    '''

    '''
    return SCRIPT_TAG.render(js_code=indent(js, 2), type=type, id=id)

# based on `html` stdlib module (3.2+)
def escape(s, quote=("'", '"')):
    """
    Replace special characters "&", "<" and ">" to HTML-safe sequences.
    If the optional flag quote is true (the default), the quotation mark
    characters, both double quote (") and single quote (') characters are also
    translated.
    """
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    if quote:
        if '"' in quote:
            s = s.replace('"', "&quot;")
        if "'" in quote:
            s = s.replace("'", "&#x27;")
    return s

#-----------------------------------------------------------------------------
# Private API
#-----------------------------------------------------------------------------

_ONLOAD = """\
(function() {
  var fn = function() {
%(code)s
  };
  if (document.readyState != "loading") fn();
  else document.addEventListener("DOMContentLoaded", fn);
})();\
"""

_SAFELY = """\
Bokeh.safely(function() {
%(code)s
});\
"""

#-----------------------------------------------------------------------------
# Code
#-----------------------------------------------------------------------------
