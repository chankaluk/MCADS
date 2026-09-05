const form = document.querySelector('#auditForm');
const text = document.querySelector('#textContent');
const fileInput = document.querySelector('#imageFile');
const dropZone = document.querySelector('#dropZone');
const previewWrap = document.querySelector('#previewWrap');
const dropPrompt = document.querySelector('#dropPrompt');
const message = document.querySelector('#formMessage');
const submit = document.querySelector('#submitButton');
const formatTime = value => {
    if (!value) return '—';
    return new Intl.DateTimeFormat('zh-CN', {
        dateStyle: 'short',
        timeStyle: 'medium'
    }).format(new Date(value))
};
async function checkHealth() {
    try {
        const response = await fetch('/health');
        if (!response.ok) throw new Error();
        const data = await response.json();
        document.querySelector('#serviceStatus').textContent = `服务在线 · ${data.version}`;
        document.querySelector('.state-dot').classList.add('online')
    } catch {
        document.querySelector('#serviceStatus').textContent = '服务暂不可用'
    }
}

function updatePreview() {
    const file = fileInput.files[0];
    if (!file) {
        previewWrap.hidden = true;
        dropPrompt.hidden = false;
        return
    }
    if (file.size > 15 * 1024 * 1024) {
        message.textContent = '图片超过15MB，请压缩后重试。';
        fileInput.value = '';
        return
    }
    document.querySelector('#previewImage').src = URL.createObjectURL(file);
    document.querySelector('#fileName').textContent = file.name;
    document.querySelector('#fileMeta').textContent = `${(file.size/1024).toFixed(1)} KB · ${file.type||'未知格式'}`;
    dropPrompt.hidden = true;
    previewWrap.hidden = false;
    message.textContent = ''
}
fileInput.addEventListener('change', updatePreview);
text.addEventListener('input', () => document.querySelector('#charCount').textContent = text.value.length);
['dragenter', 'dragover'].forEach(name => dropZone.addEventListener(name, event => {
    event.preventDefault();
    dropZone.classList.add('dragging')
}));
['dragleave', 'drop'].forEach(name => dropZone.addEventListener(name, event => {
    event.preventDefault();
    dropZone.classList.remove('dragging')
}));
form.addEventListener('reset', () => setTimeout(() => {
    text.dispatchEvent(new Event('input'));
    updatePreview();
    message.textContent = ''
}, 0));
form.addEventListener('submit', async event => {
    event.preventDefault();
    message.textContent = '';
    const file = fileInput.files[0];
    if (!text.value.trim() || !file) {
        message.textContent = '请同时提供文本和图像。';
        return
    }
    submit.disabled = true;
    submit.textContent = '正在检测…';
    const body = new FormData();
    body.append('text_content', text.value);
    body.append('image_file', file);
    body.append('trace_id', `WEB-${Date.now()}`);
    try {
        const response = await fetch('/api/v1/audit/stream', {
            method: 'POST',
            body
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || '检测失败');
        renderResult(payload.data);
        await loadHistory()
    } catch (error) {
        message.textContent = error.message
    } finally {
        submit.disabled = false;
        submit.textContent = '开始多模态检测'
    }
});

function renderResult(data) {
    document.querySelector('#emptyResult').hidden = true;
    document.querySelector('#resultContent').hidden = false;
    const score = Math.round(data.risk_score * 100);
    document.querySelector('#scoreValue').textContent = score;
    document.querySelector('#scoreRing').style.setProperty('--score', score);
    document.querySelector('#actionValue').textContent = data.action;
    document.querySelector('#modelVersion').textContent = data.model_version;
    const badge = document.querySelector('#resultBadge');
    const actionLabels = {
        BLOCK: '高风险 · 建议拦截',
        REVIEW: '中风险 · 建议复核',
        PASS: '低风险 · 建议放行'
    };
    badge.textContent = actionLabels[data.action] || data.action;
    badge.className = `result-badge ${data.action.toLowerCase()}`;
    document.querySelector('#labelList').innerHTML = data.labels.map(label => `<span>${escapeHtml(label)}</span>`).join('');
    document.querySelector('#reasonList').innerHTML = data.explanation.map(reason => `<li>${escapeHtml(reason)}</li>`).join('');
    document.querySelector('#recordId').textContent = data.record_id;
    document.querySelector('#latency').textContent = `${data.latency_ms} ms`
}
async function loadHistory() {
    const body = document.querySelector('#historyBody');
    try {
        const [historyResponse, statisticsResponse] = await Promise.all([
            fetch('/api/v1/audit/history?limit=10'),
            fetch('/api/v1/audit/statistics')
        ]);
        const payload = await historyResponse.json();
        const statistics = await statisticsResponse.json();
        if (statisticsResponse.ok) {
            document.querySelector('#totalAudits').textContent = statistics.data.total;
        }
        if (!payload.data.length) {
            body.innerHTML = '<tr><td colspan="5" class="muted">暂无检测记录</td></tr>';
            return
        }
        body.innerHTML = payload.data.map(item => `<tr><td>${escapeHtml(item.record_id)}</td><td>${(item.risk_score*100).toFixed(0)}</td><td>${escapeHtml(item.action)}</td><td>${item.labels.map(escapeHtml).join('、')}</td><td>${formatTime(item.created_at)}</td></tr>`).join('')
    } catch {
        body.innerHTML = '<tr><td colspan="5" class="muted">记录加载失败</td></tr>'
    }
}

function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
    } [char]))
}
document.querySelector('#refreshHistory').addEventListener('click', loadHistory);
checkHealth();
loadHistory();
document.querySelector('#demoButton').addEventListener('click', async () => {
    message.textContent = '';
    text.value = '请立即扫码验证账户密码，否则服务将被暂停。';
    text.dispatchEvent(new Event('input'));
    const png = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='), char => char.charCodeAt(0));
    const body = new FormData();
    body.append('text_content', text.value);
    body.append('image_file', new Blob([png], {
        type: 'image/png'
    }), 'risk-demo.png');
    body.append('trace_id', `DEMO-${Date.now()}`);
    submit.disabled = true;
    try {
        const response = await fetch('/api/v1/audit/stream', {
            method: 'POST',
            body
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || '演示检测失败');
        renderResult(payload.data);
        await loadHistory()
    } catch (error) {
        message.textContent = error.message
    } finally {
        submit.disabled = false
    }
});
