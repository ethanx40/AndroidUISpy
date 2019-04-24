# -*- coding: UTF-8 -*-
#
# Tencent is pleased to support the open source community by making QTA available.
# Copyright (C) 2016THL A29 Limited, a Tencent company. All rights reserved.
# Licensed under the BSD 3-Clause License (the "License"); you may not use this 
# file except in compliance with the License. You may obtain a copy of the License at
# 
# https://opensource.org/licenses/BSD-3-Clause
# 
# Unless required by applicable law or agreed to in writing, software distributed 
# under the License is distributed on an "AS IS" basis, WITHOUT WARRANTIES OR CONDITIONS
# OF ANY KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.
#

'''WebView调试工具
'''

import json
from utils.exceptions import WebViewDebuggingNotEnabledError

def replace_url_func_wrap(func):
    '''替换调试url
    '''
    def _func(*args, **kwargs):
        url = func(*args, **kwargs)
        return url.replace('chrome-devtools-frontend.appspot.com', 'chrome-devtools-frontend.netlify.com')
    return _func
    
class WebViewDebuggingTool(object):
    '''WebView调试工具
    '''
    def __init__(self, device):
        self._device = device
        
    def get_webview_debugging_server_list(self):
        '''获取开启WebView调试服务列表
        '''
        server_list = []
        result = self._device.adb.run_shell_cmd('cat /proc/net/unix')
        for line in result.split('\n'):
            items = line.strip().split()
            name = items[-1]
            if name.startswith('@webview_devtools_remote_'):
                if not name[1:] in server_list: server_list.append(name[1:])
        return server_list

    def get_service_name(self, process_name):
        pid = self._device.adb.get_pid(process_name)
        return 'webview_devtools_remote_%d' % pid

    def is_webview_debugging_opened(self, process_name):
        '''是否进程开启了WebView调试
        '''
        service_name = self.get_service_name(process_name)
        return service_name in self.get_webview_debugging_server_list()

    def get_page_info(self, sock, debugging_url):
        '''通过执行js获取页面标题和url
        '''
        try:
            import chrome_master
        except ImportError:
            return None, None
        if debugging_url.startswith('ws:///'):
            debugging_url = 'ws://localhost%s' % debugging_url[5:]

        debugger = chrome_master.RemoteDebugger(debugging_url, lambda: sock)
        debugger.register_handler(chrome_master.RuntimeHandler)
        url = debugger.runtime.eval_script(None, 'location.href')
        title = debugger.runtime.eval_script(None, 'document.title')
        return title, url

    def get_webview_page_list(self, process_name):
        '''获取进程打开的WebView页面列表
        '''
        service_name = self.get_service_name(process_name)
        sock = self._device.adb.create_tunnel(service_name, 'localabstract')
        if not sock: raise WebViewDebuggingNotEnabledError('WebView debugging in %s not enabled' % process_name)
        sock.send('GET /json HTTP/1.1\r\n\r\n')
        resp = sock.recv(4096)
        pos = resp.find('\r\n\r\n')
        body = resp[pos + 4:]
        print(body)
        page_list = json.loads(body)
        result = []
        for page in page_list:
            if page['type'] != 'page': continue
            desc = page['description']
            if desc:
                page['description'] = json.loads(desc)
                if not page['description'].get('width') or not page['description'].get('height'): 
                    continue
                if not page['description']['visible']: continue
            if page['url'] == 'about:blank': # and page['title'] == 'about:blank'
                # 微信小程序中发现这里返回的url和title可能都不对
                if not 'webSocketDebuggerUrl' in page:
                    raise RuntimeError('请关闭已打开的Web调试页面')
                title, url = self.get_page_info(sock, page['webSocketDebuggerUrl'])
                if not url or url == 'about:blank':
                    continue
                page['url'] = url
                page['title'] = title
            result.append(page)
        sock.close()
        return result
    
    def _get_similar(self, text1, text2):
        '''计算相似度
        '''
        import difflib
        return difflib.SequenceMatcher(None, text1, text2).ratio()
    
    @replace_url_func_wrap
    def get_debugging_url(self, process_name, multi_page_callback, url, title=None):
        '''获取WebView调试页面url
        '''
        page_list = self.get_webview_page_list(process_name)
        if len(page_list) == 1: return page_list[0].get('devtoolsFrontendUrl')
        
        if url == None and title == None:
            return multi_page_callback(page_list)
        
        for page in page_list:
            if url and self._get_similar(page['url'], url) >= 0.05: return page.get('devtoolsFrontendUrl')
            if title and page['title'] == title: return page.get('devtoolsFrontendUrl')
        else:
            raise RuntimeError(u'未找到页面：url=%s title=%s' % (url.decode('utf8'), title.decode('utf8') if title else None))
    
if __name__ == '__main__':
    pass