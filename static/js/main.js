document.addEventListener('DOMContentLoaded', function () {
  const status = document.getElementById('status');
  const btn = document.querySelector('.btn-primary');
  const form = document.getElementById('connect');

  // 新建函数: 设置默认端口
  function setDefaultPort() {
    const protocol = document.getElementById('protocol').value; // 获取协议类型
    const portField = form.querySelector('input[name="port"]'); // 获取端口字段

    if (!portField.value.trim()) {  // 检查空字符串或仅包含空白字符的情况
      if (protocol === 'telnet') {
        portField.value = '23';
      } else if (protocol === 'ssh') {
        portField.value = '22';
      }
    }
    
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault(); // 阻止表单的默认提交行为

    // 调用设置默认端口的函数
    setDefaultPort();

    const url = form.action;
    const type = form.method; // 提交方式
    const data = new FormData(form);

    // 检查 privatekey 文件大小
    const pk = data.get('privatekey');
    if (pk && pk.size > 16384) {
      status.textContent = 'Key文件大小超限!';
      return;
    }

    status.textContent = '';
    btn.disabled = true;

    // 使用 fetch 发送表单数据
    fetch(url, {
      method: type,
      body: data,
    })
      .then((response) => response.json()) // 解析返回的 JSON 数据
      .then(callback)
      .catch((error) => {
        console.error('Error:', error);
        status.textContent = '连接服务器超时，请稍后重试！';
        btn.disabled = false;
      });
  });

  function callback(msg) {
    const ws_url = window.location.origin.replace('http', 'ws'); // 获取 WebSocket 基础 URL
    const url = `${ws_url}/ws?id=${msg.id}`; // 明确拼接 `/ws` 路径
    const socket = new WebSocket(url);
    const terminal = document.getElementById('terminal');
    const term = new Terminal({ cursorBlink: true });

    console.log('WebSocket URL:', url); // 打印 WebSocket URL

    // 终端输入时发送数据到后端
    term.on('data', function (data) {
      socket.send(data);
    });

    // WebSocket 连接打开时的回调
    socket.onopen = function () {
      document.querySelector('.container').style.display = 'none';
      term.open(terminal, true);
      term.toggleFullscreen(true);
    };

    // WebSocket 接收到数据时的回调
    socket.onmessage = function (msg) {
      term.write(msg.data);
    };

    // WebSocket 错误处理
    socket.onerror = function (e) {
      console.error('WebSocket error:', e);
    };

    // WebSocket 关闭时的回调
    socket.onclose = function (e) {
      console.log('WebSocket closed:', e);
      term.destroy();
      document.querySelector('.container').style.display = 'block';
      status.textContent = e.reason;
      btn.disabled = false;
    };
  }

  // 协议选择变化时的处理
  document.getElementById('protocol').addEventListener('change', function() {
      var selectElement = document.getElementById('protocol');
      var selectedText = selectElement.options[selectElement.selectedIndex].text;
      console.log('Selected protocol:', selectedText);
      if (selectedText === 'SSH') {
      sshOnlyFields.style.display = ''; // 显示 SSH 字段
      } else if (selectedText === 'Telnet') {
      sshOnlyFields.style.display = 'none'; // 隐藏 SSH 字段
      }
  });

});
