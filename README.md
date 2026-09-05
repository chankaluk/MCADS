# 基于深度学习的多模态内容异常检测系统 V1.0

MCADS 接收文本和图像，输出风险分数、风险等级、处置建议、风险标签和检测原因。当前默认后端采用可复现的混合特征融合；项目同时保留 PyTorch 双向交叉注意力网络接口，便于后续接入训练权重。

## 功能

- 文本与图像联合输入校验；
- 15MB 上传限制和图像完整性检查；
- 实时风险检测接口；
- 文本结构特征与图像视觉统计特征提取；
- PASS、REVIEW、BLOCK 三级风险处置；
- 可解释风险标签和特征摘要；
- 本地 Web 检测控制台；
- 脱敏审计日志、坏行容错、历史记录和聚合统计；
- 可选 PyTorch 跨模态网络；
- 自动语法与功能检查。

## 安装

建议使用 Python 3.10—3.12：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows 激活命令为 `.venv\\Scripts\\activate`。

## 启动

```bash
uvicorn api_gateway:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/` 使用检测控制台；接口文档位于 `/docs`，健康检查位于 `/health`。

## 检查

```bash
python generate_code.py --check
python -m unittest discover -s tests -v
```

## 主要接口

- `POST /api/v1/audit/stream`：提交 `text_content`、`image_file` 和可选 `trace_id`；
- `GET /api/v1/audit/history?limit=20`：读取最近的脱敏检测记录；
- `GET /api/v1/audit/statistics`：读取累计检测、处置数量和平均风险分；
- `GET /health`：查看服务和版本状态。

## 目录

```text
MCADS_Project/
├── static/                 # Web控制台
├── tests/                  # 自动化测试
├── logs/                   # 运行日志（不进入版本库）
├── feature_extractor.py    # 文本与图像特征提取
├── risk_policy.py          # 风险策略与三级处置
├── audit_repository.py     # 审计仓储与统计
├── core_engine.py          # 风险引擎与可选神经网络
├── dataset_loader.py       # 输入和图像校验
├── api_gateway.py          # HTTP服务与历史记录
└── generate_code.py        # 项目检查
```

## 当前限制

默认运行后端尚未接入训练后的 BERT/ViT 权重，因此不能把混合特征结果解释为正式深度学习模型性能。正式部署前还应补充合规数据集、模型权重、指标评测、认证、HTTPS、限流和数据库存储。
