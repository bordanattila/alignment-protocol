"""Read-only Sites identity canary. Cookies stay in this local process only.

Only the two release-probe paths on the fixed Site are contacted. No mission
endpoint, backend, provider, redirect or persistent cookie storage is used.
"""
import argparse
import base64
import getpass
import http.client
import json
import os
import ssl

HOST='consensus-engine-playtest.justfrog18.chatgpt.site'
ORIGIN='https://'+HOST
CASES={
 'base':[],
 'id':[('oai-authenticated-user-id','ce-canary-forged-other-account')],
 'email':[('oai-authenticated-user-email','forged@example.invalid'),('oai-authenticated-user-full-name','Forged Person')],
 'duplicate':[('oai-authenticated-user-id','ce-canary-forged-one'),('oai-authenticated-user-id','ce-canary-forged-two'),
              ('oai-authenticated-user-email','first@example.invalid'),('oai-authenticated-user-email','second@example.invalid')],
 'mixed':[('OaI-AuThEnTiCaTeD-UsEr-Id','ce-canary-mixed'),('oai-authenticated-user-id','ce-canary-forged-two'),
          ('OaI-AuThEnTiCaTeD-UsEr-EmAiL','first@example.invalid'),('oai-authenticated-user-email','second@example.invalid')],
 'proxy':[('X-Consensus-Visitor','a'*64),('X-Consensus-Gateway-Key','not-the-real-key'),
          ('X-Forwarded-For','192.0.2.1'),('Forwarded','for=192.0.2.1'),('X-Real-IP','192.0.2.2')],
}


def probe(account,cookie='',anonymous=False,connection_factory=None):
    if account not in ('a','b'):raise ValueError('Use account a or b')
    if len(cookie)>16384 or any(ord(c)<32 or ord(c)>126 for c in cookie):raise ValueError('Invalid Cookie header')
    if not anonymous and not cookie.strip():raise ValueError('A signed-in Site Cookie header is required')
    results=[]
    factory=connection_factory or (lambda:http.client.HTTPSConnection(HOST,443,timeout=12,context=ssl.create_default_context()))
    for transport in ('http','ws'):
        for case,extra in CASES.items():
            label=f'{account}-{transport}-{case}'
            path='/api/release-probe'+('/ws' if transport=='ws' else '')+'?case='+label
            connection=factory()
            try:
                connection.putrequest('GET',path,skip_accept_encoding=True)
                connection.putheader('Origin',ORIGIN)
                connection.putheader('Cache-Control','no-store')
                connection.putheader('X-Consensus-Canary-Case',label)
                if cookie:connection.putheader('Cookie',cookie)
                if transport=='ws':
                    connection.putheader('Connection','Upgrade')
                    connection.putheader('Upgrade','websocket')
                    connection.putheader('Sec-WebSocket-Version','13')
                    connection.putheader('Sec-WebSocket-Key',base64.b64encode(os.urandom(16)).decode())
                for name,value in extra:connection.putheader(name,value)
                connection.endheaders()
                response=connection.getresponse();status=response.status
                # Never echo response headers/cookies/authentication redirects.
                response.read(1024)
                expected=401 if anonymous else 503
                safe=status==expected or (case!='base' and status in (400,403))
                results.append({'case':label,'status':status,'expected_or_rejected':safe})
                if not safe:return {'passed':False,'anonymous':anonymous,'account':account,'checks':results,'stop':True}
            except Exception as error:
                return {'passed':False,'anonymous':anonymous,'account':account,'checks':results,
                        'error_type':type(error).__name__,'stop':True}
            finally:connection.close()
    return {'passed':True,'anonymous':anonymous,'account':account,'checks':results,
            'dual_identity_fingerprints_require_operator_log_comparison':True,'mission_writes':0,'provider_calls':0}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self,message):
            # Never echo accidentally pasted cookie material from arguments.
            self.exit(2,'Invalid command arguments. Copy the command without punctuation, press Enter, and wait for the hidden Cookie prompt.\n')
    parser=SafeParser(description=__doc__)
    parser.add_argument('--account',choices=['a','b'],required=True)
    parser.add_argument('--anonymous',action='store_true')
    args=parser.parse_args()
    cookie='' if args.anonymous else getpass.getpass('Paste ONLY this profile\'s Site Cookie header (hidden; never send it to chat): ')
    result=probe(args.account,cookie,args.anonymous)
    cookie=''
    print(json.dumps(result,separators=(',',':')))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
