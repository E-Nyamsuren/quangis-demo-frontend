from __future__ import annotations

from django.shortcuts import render

# Create your views here.
from django.conf import settings
from django.template import loader

from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseBadRequest, JsonResponse

import json

import zmq
import uuid

from rdflib import RDF
from rdflib.term import BNode
from transformation_algebra import \
    TransformationGraph, TransformationQuery, TA
from transformation_algebra.type import Product, TypeOperation
from cct.language import cct, R3, R2, Obj, Reg

from transformation_algebra.util.store import MarkLogic

wf_store = MarkLogic(
    url=settings.TDB_URL,   
    cred=(settings.TDB_USER, settings.TDB_PASS)
)


# [SC] for testing
# from django.apps import apps


def question2query(queryEx: dict) -> TransformationQuery:
    """
    Converts a query formatted as a dictionary into a `TransformationQuery`,
    which can be in turn translated to a SPARQL query.
    """
    # This should probably go in a more sane place eventually, when the
    # structure of the modules is more stable

    g = TransformationGraph(cct)
    task = BNode()
    g.add((task, RDF.type, TA.Task))

    def f(q: dict) -> BNode:
        node = BNode()
        t = cct.parse_type(q['after']['cct']).concretize(replace=True)

        # This is a temporary solution: R(x * z, y) is for now converted to the
        # old-style R3(x, y, z)
        if isinstance(t.params[0], TypeOperation) and \
                t.params[0].operator == Product:
            t = R3(t.params[0].params[0], t.params[1], t.params[0].params[1])

        # Another temporary solution. the question parser often returns `R(Obj,
        # x)` where the manually constructed queries ("gold standard") would
        # use `R(Obj, Reg * x)`. So, whenever we encounter the former, we will
        # manually also allow the latter
        # cf. <https://github.com/quangis/transformation-algebra/issues/79#issuecomment-1210661153>
        if isinstance(t.params[0], TypeOperation) and \
                t.operator == R2 and \
                t.params[0].operator == Obj and \
                t.params[1].operator != Product:
            g.add((node, TA.type, cct.uri(R2(t.params[0], Reg * t.params[1]))))

        g.add((node, TA.type, cct.uri(t)))
        for b in q.get('before') or ():
            g.add((node, TA['from'], f(b)))

        return node

    g.add((task, TA.output, f(queryEx)))
    return TransformationQuery(cct, g)


def question2parsetree(qStr):
    # [SC][TODO] exception handling
    # [SC] make sure client has a unique id otherwise client request may be ignored
    identity = f"client-{uuid.uuid1()}"
    
    # [SC] opening a connection to the service
    print("Starting the question parser client")
    context = zmq.Context()
    socket = context.socket(zmq.DEALER)
    socket.setsockopt_string(zmq.IDENTITY, identity)
    socket.connect(f"tcp://{settings.QPARSE_IP}:{settings.QPARSE_PORT}")
    
    print("Setting the question parser client poller")
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    # [SC] send a request
    print("Sending a request to the remote question parser service")
    socket.send_string(qStr)

    # [SC] wait for a reply
    print("Waiting for a reply ...")
    msg = None
    while True:
        # [SC] wait for 60 seconds for a message to arrive, otherwise terminate
        sockets = dict(poller.poll(settings.QPARSE_WAIT))
        if sockets:
            if sockets.get(socket) == zmq.POLLIN:
                msg = socket.recv_string()
                print(f"Question parser client received a reply: {msg}")
                break
        else:
            break

    socket.close()
    context.term()
    
    return msg


def parseQuestion(qStr):
    print(f"Processing a new request with question '{qStr}'")

    response = question2parsetree(qStr)
    
    if not response:
        return {"error": "No response from the question parsing service."}

    qParsed = json.loads(response)
    
    if "error" in qParsed:
        return qParsed

    try:
        # Query for matches
        print("Generating a SPARQL query")
        query = question2query(qParsed['queryEx'])
        qParsed['sparql'] = query.sparql()
        print("Querying the triple database")
        qParsed['matches'] = matches = [str(wf) for wf in wf_store.query(query)]

        # Add the first match as JSON-LD
        if matches:
            g = wf_store.get(matches[0])
            qParsed['workflow'] = json.loads(g.serialize(format="json-ld"))
        else:
            qParsed['workflow'] = None

        return qParsed
    except Exception as e:
        print("============================ Exception while querying for workflows:")
        print(e)
        return {"error": "Exception while querying for workflows."}


# [SC] for retrieving by URI a workflow graph on demand from the client
def retrieveWfGraphAsync(request):
    print("========================= request from " + get_client_ip(request))
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if is_ajax:
        if request.method == 'GET':
            garphId = request.GET.get('graphId', '')
            
            g = wf_store.get(garphId)
            jsonLd = json.loads(g.serialize(format="json-ld"))

            return JsonResponse(jsonLd, safe=False)
        return JsonResponse({'status': 'Invalid request'}, status=400)
    else:
        return HttpResponseBadRequest('Invalid request')
    


def loadBlocklyUI(request):
    print("========================= request from " + get_client_ip(request))
    
    context = {}
    return render(request, 'blocklyUI/index.html', context)

def loadDemo(request):
    print("========================= request from " + get_client_ip(request))
    
    context = {}
    return render(request, 'blocklyUI/demo.html', context)

def loadTutorials(request):
    print("========================= request from " + get_client_ip(request))
    
    context = {}
    return render(request, 'blocklyUI/tutorials.html', context)
    
def loadDocsTool(request):
    print("========================= request from " + get_client_ip(request))
    
    context = {}
    return render(request, 'blocklyUI/docs-tool.html', context)
    
def loadDocsCCD(request):
    print("========================= request from " + get_client_ip(request))
    
    context = {}
    return render(request, 'blocklyUI/docs-ccd.html', context)
    
def loadDocsAlgebra(request):
    print("========================= request from " + get_client_ip(request))
    
    context = {}
    return render(request, 'blocklyUI/docs-algebra.html', context)

def loadAbout(request):
    print("========================= request from " + get_client_ip(request))
    
    context = {}
    return render(request, 'blocklyUI/about.html', context)



# [SC][TODO] remove the function    
def processNlpQuestion(request):
    print("========================= request from " + get_client_ip(request))
    
    qStr = request.GET['qStr']
    qParsed = parseQuestion(qStr)

    return HttpResponse(json.dumps(qParsed) + "<br><br><a href='/'>Go back</a>")
    
    # [SC][DELETE] for testing
    #return HttpResponse("Received and sent back this question: %s." % request.GET['qStr']) # [SC][DELETE]

    
def processNlpQuestionAsync(request):
    print("========================= request from " + get_client_ip(request))

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if is_ajax:
        if request.method == 'GET':
            qStr = request.GET.get('qStr', '')
            qParsed = parseQuestion(qStr)
            
            return JsonResponse(qParsed) # [SC][TODO] remove the array form in the output of parse_Question
        return JsonResponse({'status': 'Invalid request'}, status=400)
    else:
        return HttpResponseBadRequest('Invalid request')
    
    # [SC][DELETE] for testing
    #myModel = apps.get_model('questionParser', 'parseQuestion')
    #return HttpResponse("Received and sent back this question: %s." % request.GET['qStr']) # [SC][DELETE]
        

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip