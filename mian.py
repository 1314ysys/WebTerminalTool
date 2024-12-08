import asyncio
import os
import uuid
import logging
import traceback
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
import paramiko
import telnetlib
import uvicorn
from fastapi import Form

app = FastAPI()

# 挂载静态文件目录，用于服务 CSS、JS 和图片
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 模板引擎设置
base_dir = os.path.dirname(__file__)
templates_env = Environment(loader=FileSystemLoader(os.path.join(base_dir, "templates")))

BUF_SIZE = 4096  # 数据缓冲区大小
workers = {}  # 用于存储活跃的 Worker 实例


class Worker:
    """
    用于管理 SSH 或 Telnet 连接的 Worker 类
    """
    def __init__(self, connection, reader, writer, dst_addr, protocol):
        self.connection = connection
        self.reader = reader
        self.writer = writer
        self.dst_addr = dst_addr
        self.protocol = protocol

        if protocol == 'ssh':
            self.fd = writer.fileno()
        elif protocol == 'telnet':
            self.fd = connection.sock.fileno() if connection else None
        else:
            # raise ValueError(f"不支持的协议: {protocol}")
            logging.error(f"不支持的协议: {protocol}")
            self.close()

        self.id = str(uuid.uuid4())
        self.data_to_dst = []  # 待发送的数据队列
        self.handler = None  # 关联的 WebSocket 处理器
        self.queue = asyncio.Queue()  # 用于消息的异步队列

    def set_handler(self, handler):
        """
        绑定 WebSocket 处理器
        """
        if not self.handler:
            self.handler = handler

    async def on_read(self):
        """
        读取远程端的数据
        """
        try:
            data = ""
            if self.protocol == 'telnet' and self.connection:
                data = self.connection.read_eager().decode('utf-8', errors='replace')
            elif self.protocol == 'ssh' and self.reader:
                if self.reader.recv_ready():
                    data = self.reader.recv(BUF_SIZE).decode('utf-8', errors='replace')

            if data:
                logging.debug(f'从 {self.dst_addr} 收到数据: "{data}"')
                if self.handler:
                    await self.handler.send_text(data)

        except Exception as e:
            logging.error(f'{e}')
            await self.close()

    async def on_write(self):
        """
        将数据发送到远程端
        """
        if not self.data_to_dst:
            return

        data = ''.join(map(str, self.data_to_dst))
        logging.debug(f'向 {self.dst_addr} 发送数据: "{data}"')

        try:
            if self.protocol == 'telnet' and self.connection:
                if self.connection.sock._closed:
                    logging.error("Telnet connection is already closed")
                    await self.close()
                    return
                self.connection.write(data.encode('utf-8'))
            elif self.protocol == 'ssh' and self.writer:
                self.writer.send(data.encode('utf-8'))
            else:
                logging.error(f"该链接已超时!")
                await self.close()
        except Exception as e:
            logging.error(f'写入数据时出错: {e}')
            await self.close()
        else:
            self.data_to_dst = []

    async def close(self):
        """
        关闭 Worker
        """
        if self.handler is None:
            return

        logging.debug(f'关闭 Worker {self.id}')
        
        try:
            # 只有在 WebSocket 连接未关闭时才尝试关闭
            if self.handler.client_state == "CONNECTED":
                await self.handler.close()
            
            # 对连接有效性进行检查
            if self.protocol == 'telnet' and self.connection:
                if hasattr(self.connection, 'sock') and not self.connection.sock._closed:  # 检查连接是否已经关闭
                    self.connection.close()
                    logging.error('Telnet connection closed')  # 打印一条连接关闭日志
            elif self.protocol == 'ssh' and self.connection:
                if hasattr(self.connection, '_transport') and self.connection._transport.is_active():
                    self.connection.close()
                    logging.error('SSH connection closed')  # 打印一条连接关闭日志
        except Exception as e:
            logging.error(f'关闭连接时出错: {e}')
        finally:
            logging.info(f'与 {self.dst_addr} 的连接已断开')
            # 清理 Worker 实例
            self.cleanup()

    def cleanup(self):
        """
        清理 Worker 资源并退出
        """
        logging.info(f"正在清理 Worker {self.id} 资源并退出...")
        if self.id in workers:
            del workers[self.id]  # 从 workers 中移除 Worker
        self.connection = None
        self.reader = None
        self.writer = None
        self.handler = None

        # 如果连接已经关闭，自动退出
        if self.protocol == 'telnet' and self.connection and hasattr(self.connection, 'sock') and self.connection.sock._closed:
            logging.info(f"Telnet connection for {self.dst_addr} 已关闭，自动退出")
            self.connection = None
            return
        if self.protocol == 'ssh' and self.connection and hasattr(self.connection, '_transport') and not self.connection._transport.is_active():
            logging.info(f"SSH connection for {self.dst_addr} 已关闭，自动退出")
            self.connection = None
            return


@app.get("/", response_class=HTMLResponse)
async def index():
    """
    返回主页 HTML
    """
    template = templates_env.get_template("index.html")
    content = template.render()
    return HTMLResponse(content=content)


@app.post("/connect")
async def connect(
    hostname: str = Form(...),
    port: int = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    protocol: str = Form(...),
):
    # 获取其他参数并执行连接逻辑
    dst_addr = f"{hostname}:{port}"
    worker_id = None
    try:
        if protocol == "ssh":
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname, port=int(port), username=username, password=password, timeout=6)

            chan = ssh.invoke_shell(term="xterm")
            chan.setblocking(0)
            worker = Worker(ssh, chan, chan, dst_addr, "ssh")
        elif protocol == "telnet":
            connection = telnetlib.Telnet(hostname, port=int(port), timeout=10)
            worker = Worker(connection, None, None, dst_addr, "telnet")
        else:
            raise ValueError("Unsupported protocol")

        workers[worker.id] = worker
        worker_id = worker.id
        logging.info(f"Worker {worker_id} connected to {dst_addr} using {protocol}")
        return JSONResponse({"id": worker_id, "status": "success"})
    except Exception as e:
        logging.error(traceback.format_exc())
        return JSONResponse({"id": worker_id, "status": f"Error: {str(e)}"})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    处理 WebSocket 通信
    """
    await websocket.accept()
    worker_id = websocket.query_params.get("id")
    worker = workers.pop(worker_id, None)
    if not worker:
        await websocket.close(reason="连接失败！请检查输入信息！")
        return

    worker.set_handler(websocket)

    # 创建并发任务来同时处理读写
    async def read_write_worker():
        while True:
            await asyncio.gather(worker.on_read(), worker.on_write())

    asyncio.create_task(read_write_worker())  # 使用协程任务

    try:
        while True:
            data = await websocket.receive_text()
            worker.data_to_dst.append(data)
    except WebSocketDisconnect:
        logging.info("WebSocket 已断开")
        await worker.close()
    except Exception as e:
        logging.error(f"WebSocket 出错: {e}")
        await worker.close()


if __name__ == "__main__":
    # 使用标准的 uvicorn 服务器启动 FastAPI 应用
    uvicorn.run(app, host="0.0.0.0", port=8886, log_level="info", loop="asyncio")
