"""Loopback-only browser fixture; explicit fake inference and isolated SQLite.

Never expose this test control API publicly. No production routes are modified.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import time

import uvicorn
from fastapi import HTTPException, Request
from app.main import create_app
from app.generation.config import GenerationSettings
from app.generation.contract import FailureCategory, GenerationError
from app.generation.endgame import EndgameRequest
from app.generation.provider import ProviderResponse
from test_live_generation import ProgressiveProvider
from test_adaptive_narrative import story


def fixture_app(directory: Path):
    config_path=directory/'config.json'
    clock_path=directory/'clock'
    if not clock_path.exists():clock_path.write_text(str(1700000000-time.time()))
    if not config_path.exists():config_path.write_text(json.dumps({'profile':'main','delay':26}))

    class Provider(ProgressiveProvider):
        async def generate(self, request):
            config=json.loads(config_path.read_text())
            endgame=isinstance(request,EndgameRequest)
            number=None if endgame else request.context.current_crisis_number
            with (directory/'attempts.jsonl').open('a') as stream:
                stream.write(json.dumps({'profile':config['profile'],'operation':'endgame' if endgame else 'crisis','crisis_number':number})+'\n')
            if endgame:return ProviderResponse(json.dumps(story(request)),200)
            if config['profile']=='main':
                if number==2:await asyncio.sleep(config['delay'])
                if number==3:raise GenerationError(FailureCategory.UNAVAILABLE,503)
                if number==4:raise GenerationError(FailureCategory.TIMEOUT)
            response=await super().generate(request)
            if config['profile']=='defeat':
                raw=json.loads(response.content)
                effects=[(-24,3,1,1),(-23,2,1,1),(-22,1,2,0)]
                for choice,values in zip(raw['crisis']['choices'],effects):
                    choice['metric_deltas']=dict(zip(('infrastructure','public_trust','economy','safety'),values))
                response=ProviderResponse(json.dumps(raw),200)
            return response

    # Explicit settings/provider ensure operator environment and real API keys
    # are never loaded or used by the served fixture application.
    app=create_app(clock=lambda:time.time()+float(clock_path.read_text()),database_path=directory/'missions.sqlite3',
        generation_settings=GenerationSettings(enabled=os.environ.get('CE_BROWSER_ACCESS_TEST')!='true',model='fixture',timeout_seconds=60),
        generation_provider=Provider())

    @app.post('/__acceptance/control')
    async def control(request: Request):
        if request.headers.get('X-Acceptance-Key')!=os.environ['CE_BROWSER_TEST_KEY']:
            raise HTTPException(403)
        body=await request.json()
        if body['action']=='expire':
            async with app.state.lock:
                mission=app.state.missions.get(body['token'])
                if mission.deadline is None:raise HTTPException(409)
                temporary=clock_path.with_suffix('.new');temporary.write_text(str(mission.deadline-time.time()));temporary.replace(clock_path)
            await app.state.tick()
        elif body['action']=='profile':
            if body['profile'] not in ('main','defeat'):raise HTTPException(400)
            config_path.write_text(json.dumps({'profile':body['profile'],'delay':float(body.get('delay',26))}))
        elif body['action']=='elapse':
            seconds=float(body.get('seconds',1))
            if not 0 < seconds <= 5:raise HTTPException(400)
            temporary=clock_path.with_suffix('.new')
            temporary.write_text(str(float(clock_path.read_text())+seconds));temporary.replace(clock_path)
        elif body['action']!='status':raise HTTPException(400)
        attempts=[json.loads(line) for line in (directory/'attempts.jsonl').read_text().splitlines()] if (directory/'attempts.jsonl').exists() else []
        response={'attempts':attempts,'lifecycle':list(app.state.generation.lifecycle)}
        if body.get('token'):
            mission=app.state.missions.get(body['token'])
            response['diagnostics']=[r.model_dump(mode='json') for r in mission.generation_diagnostics]
        return response
    # create_app's catch-all static mount must remain after this test-only API.
    app.router.routes.insert(0, app.router.routes.pop())
    return LocalAccessFixture(app, os.environ.get('CE_BROWSER_ACCESS_TEST') == 'true')


class LocalAccessFixture:
    """Loopback TEST adapter; never copied into Docker's backend/app source.

    Models dispatch sign-in/cancellation for UI acceptance, NOT real SIWC or
    public-header sanitization. All real platform/network requests are blocked
    by the browser harness. Existing gameplay tests use an explicitly signed-in
    fixture; access tests require a local fake cookie. No production auth code.
    """
    def __init__(self, app, require_cookie):
        self.app, self.require_cookie = app, require_cookie

    async def __call__(self, scope, receive, send):
        from http.cookies import SimpleCookie
        from urllib.parse import parse_qs, urlencode, urlsplit
        from html import escape
        from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
        import re
        headers = dict(scope.get('headers', []))
        cookie = SimpleCookie()
        try: cookie.load(headers.get(b'cookie', b'').decode())
        except Exception: pass
        signed_in = not self.require_cookie or ('ce-local-account' in cookie and cookie['ce-local-account'].value in ('fixture-a', 'fixture-b'))
        path = scope.get('path', '')
        if scope['type'] == 'http':
            if path == '/api/access':
                return await JSONResponse({'signedIn': signed_in}, headers={'Cache-Control': 'no-store'})(scope, receive, send)
            if path in ('/signin-with-chatgpt', '/signout-with-chatgpt', '/__local/confirm-signin'):
                query = parse_qs(scope.get('query_string', b'').decode())
                target = query.get('return_to', ['/'])[0]
                parsed = urlsplit(target)
                invite = parse_qs(parsed.query).get('mission', [])
                target = '/?'+urlencode({'mission': invite[0]}) if target.startswith('/') and not target.startswith('//') and not parsed.netloc and parsed.path == '/' and len(invite)==1 and re.fullmatch('[A-Za-z0-9_-]{1,128}',invite[0]) else '/'
                if path == '/signin-with-chatgpt':
                    confirm = '/__local/confirm-signin?'+urlencode({'return_to': target})
                    response = HTMLResponse('<h1>Local sign-in fixture</h1><a href="'+escape(confirm)+'">Confirm local sign-in</a> <a href="'+escape(target)+'">Cancel sign-in</a>')
                else:
                    response = RedirectResponse(target, status_code=303)
                    if path == '/signout-with-chatgpt': response.delete_cookie('ce-local-account')
                    else: response.set_cookie('ce-local-account', 'fixture-a', httponly=True, samesite='lax')
                return await response(scope, receive, send)
        if path.startswith('/api/') and not signed_in:
            if scope['type'] == 'websocket': return await send({'type':'websocket.close','code':1008})
            return await JSONResponse({'detail':'Sign in with ChatGPT to play.'}, status_code=401)(scope, receive, send)
        return await self.app(scope, receive, send)


if __name__=='__main__':
    folder=Path(sys.argv[1]).resolve()
    if not folder.is_dir() or not folder.name.startswith('ce97-private-'):
        raise SystemExit('Requires a new isolated ce97-private-* directory')
    uvicorn.run(fixture_app(folder),host='127.0.0.1',port=int(sys.argv[2]),log_level='warning',access_log=False)
