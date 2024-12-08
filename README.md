# WebTerminalTool
这是一个简单的支持**ssh**协议与**telnet**协议的web终端。适合集成到各类需要远程连接的管理后台网站。

*!!!本项目修改自 https://github.com/WalkerWang731/WebTerminal 的工程。!!!*
# 修改详情
- 增加了对于**Telnet**协议的支持
- 移除了Jquery.js的依赖，使用Javascripts原生语法
- Web框架从Tornado修改为流行的的FastAPI+Uvicorn的方式
# 如何运行
(开发环境为Python3.10,为免异常请使用这个版本)

1.下载源码

2.创建并激活虚拟环境(可选)
```
python -m venv myenv
```
```
myenv\Scripts\activate
```
3.安装依赖
```
pip install -r requirements.txt
```
4.运行主程序
```
python main.py
```
5.浏览器打开**本机IP:8886**地址打开网页
注：如果前端不输入端口号则默认使用各协议的默认端口。**ssh协议22；telnet协议23**
