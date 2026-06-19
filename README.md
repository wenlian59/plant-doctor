# Plant Doctor - 后端

植物病害诊断后端服务。流程分两步：

1. **分类模型**（本地 MobileNetV2，38 类病害识别）对上传图片做初步分类，得到病害类别 + 置信度
2. **Gemini API** 结合分类结果和原图，生成详细诊断报告（常见名、学名、健康状态、养护建议等）
   （后来改成使用Qwen-VL-max模型）

技术栈：Python + FastAPI + Transformers (PyTorch)

## 目录结构

```
plant-doctor-main/
├── .env.local                      # 环境变量（Gemini key、代理配置）
├── requirements.txt                # Python 依赖
├── mobilenet_v2_plant_disease/     # 分类模型权重 (HuggingFace 格式)
├── data/history.json               # 历史记录（运行后自动生成，已加入 .gitignore）
├── uploads/                        # 原图与缩略图（运行后自动生成，已加入 .gitignore）
└── app/
    ├── main.py                     # FastAPI 入口，定义 /api/diagnose 接口
    ├── config.py                   # 读取环境变量、模型路径等配置
    ├── schemas.py                  # 请求/响应数据结构
    ├── classifier.py               # 加载模型，执行图片分类
    └── gemini_client.py            # 封装 Gemini API 调用（拼 prompt、解析返回）
```

## 环境要求

- Python 3.10+
- 已安装的关键依赖（版本不严格要求，详见 `requirements.txt`）：
  `fastapi`、`uvicorn`、`transformers`、`torch`、`pillow`、`httpx`、`python-multipart`、`python-dotenv`

## 启动手册

### 1. 安装依赖

如果环境里还没有这些包：

```bash
pip install -r requirements.txt
```

> 如果包已安装且版本较新（如 `transformers` 4.45+），无需重新安装，直接跳过此步即可。

### 2. 配置环境变量

项目根目录下的 `.env.local` 文件需要包含：

```
# Gemini API Key，在 https://aistudio.google.com/apikey 免费申请
GEMINI_API_KEY=你的key

# 代理地址（国内直连 Gemini 受限时需要，本地没有代理则删掉这一行）
PROXY_URL=http://127.0.0.1:7897
```
千问的api不需要加代理地址
> ⚠️ `.env.local` 不要提交到 Git（已加入 `.gitignore`）。如果你的 key 曾经在聊天记录、截图等地方暴露过，请去 Google AI Studio 重新生成。

#### 关于 `PROXY_URL`（重要，换机器/部署时必看）

国内网络通常无法直连 Gemini API，后端调用 Gemini 时会通过 `PROXY_URL` 指定的代理转发请求。这个值**和运行后端的那台机器强相关**：

- `http://127.0.0.1:7897` 是当前开发机上代理软件（如 Clash）监听的本地端口，**换一台机器大概率不是这个端口**
- 部署/交接到其他人电脑时，需要改成那台机器上代理软件实际监听的地址和端口
- 如果运行环境本身能直连 Gemini（比如服务器在国外，或者网络不受限），把这一行删掉即可，代码里没有配置时会直接发起请求，不走代理
- 如果忘记改这一项，现象通常是：`/api/diagnose` 接口很快返回 `success: false`，`message` 里提示连接 Gemini 失败或超时

排查时可以先单独确认代理软件本身正常工作（比如用浏览器走同一个代理访问 Google），再排查后端配置。

### 3. 启动服务

在 `plant-doctor-main/` 目录下运行：

```bash
python -m uvicorn app.main:app --reload --port 8000
```

启动成功后访问：

- 健康检查：http://127.0.0.1:8000/health
- 交互式接口文档（Swagger UI）：http://127.0.0.1:8000/docs

### 4. 测试接口

用 `curl` 上传一张图片测试：

```bash
curl -X POST http://127.0.0.1:8000/api/diagnose -F "image=@你的图片路径.jpg"
```

或者直接打开 http://127.0.0.1:8000/docs，在网页里上传图片测试。

## 接口说明

接口结构严格对照前端提供的 `api.ts` 类型定义实现，所有响应都包一层 `{ success, data, message }`。

### `POST /api/diagnose`

**请求**：`multipart/form-data`，字段名 `image`，值为图片文件

**响应**（节选）：

```json
{
  "success": true,
  "record_id": "rec_1749123456789_abc",
  "data": {
    "identifier": {
      "common_name": "白芥",
      "scientific_name": "Sinapis alba",
      "family": "十字花科",
      "confidence": 0.95,
      "about": "...",
      "tags": ["一年生植物", "原产地：地中海"],
      "edible_parts": ["叶子", "种子"],
      "common_aliases": ["黄芥子", "White Mustard"]
    },
    "schedule": {
      "soil_type": "排水良好的壤土或沙质土，微碱性为佳",
      "fertilizer": "生长初期施富氮肥料，之后每3-4周轻量追肥",
      "weekly": [
        { "day": "周一", "water_ml": 50, "sunlight_hours": "6-8小时" },
        { "day": "周日", "water_ml": null, "sunlight_hours": "6-8小时" }
      ]
    },
    "diagnosis": {
      "health_status": "diseased",
      "disease_name": "早疫病",
      "pathogen": "Alternaria solani（链格孢菌）",
      "severity": "moderate",
      "confidence": 0.85,
      "symptoms": ["..."],
      "treatments": [{ "title": "杀菌剂试用", "detail": "..." }],
      "prevention": ["..."]
    }
  },
  "message": null
}
```

字段来源说明：
- `identifier.confidence`：本地分类模型给出的置信度
- `diagnosis.confidence`：Gemini 对本次诊断结论给出的置信度
- `health_status`/`severity`：固定英文枚举值（`"healthy"|"diseased"`、`"low"|"moderate"|"high"|null`），其余文本字段均为中文
- `water_ml`：数字（毫升）或 `null`（表示当天无需浇水）
- `identifier.about`：长度控制在 100 字以内

**失败时**（`success: false`），`message` 字段固定返回以下错误码字符串之一（与 `api.md` 约定一致）：

| message 值 | 含义 | 触发场景 |
| --- | --- | --- |
| `not_a_plant` | 图片中未检测到植物 | 上传了非植物图片 |
| `image_too_large` | 图片超过 10MB | 图片文件过大 |
| `model_timeout` | 模型/Gemini 推理超时 | 服务器繁忙或响应慢 |
| `unsupported_format` | 不支持的图片格式 | 非 jpg/png/webp，或文件无法解析 |
| `record_not_found` | 历史记录不存在 | 传入了无效的 record_id |
| `internal_error` | 服务器内部错误 | 其他未知异常（含 Gemini key 缺失、返回格式异常等）|

### `GET /api/history?page=1&limit=10`

返回历史记录分页列表：

```json
{
  "success": true,
  "total": 12,
  "page": 1,
  "limit": 10,
  "data": [
    {
      "record_id": "rec_1749123456789_abc",
      "created_at": "2026-06-07T12:00:56Z",
      "thumbnail": "/uploads/thumb_rec_1749123456789_abc.jpg",
      "common_name": "白芥",
      "scientific_name": "Sinapis alba",
      "health_status": "diseased",
      "disease_name": "早疫病"
    }
  ],
  "message": null
}
```

### `GET /api/history/{record_id}`

返回单条历史记录的完整诊断结果（结构同 `/api/diagnose` 的 `data`，并附加 `record_id`、`created_at`、`image_url`）。

### `DELETE /api/history/{record_id}`

删除一条记录及其图片文件，返回 `{ "success": true }`。

### `GET /health`

健康检查，正常时返回 `{"status": "ok"}`

## 数据存储

- 历史记录保存在项目根目录下的 `data/history.json`（首次启动自动创建，按时间倒序存放完整诊断结果）
- 上传的原图与缩略图保存在 `uploads/` 下，命名为 `{record_id}.jpg` / `thumb_{record_id}.jpg`，并通过 `/uploads/...` 路径对外提供静态访问
- `record_id` 格式为 `rec_<毫秒时间戳>_<3位随机字符>`，如 `rec_1749123456789_abc`
- `data/`、`uploads/` 均已加入 `.gitignore`，不会被提交到 Git

> 以上存储格式、路径与命名均按 `api.md`（联调同学维护的"前后端联调唯一标准"）对齐。

## 给前端的对接说明

- 后端默认运行在 `http://localhost:8000`，前端请求时需要把接口地址指向这里（建议放到一个环境变量里，比如 `NEXT_PUBLIC_API_URL`）
- 已开启 CORS（允许所有来源），前端可直接跨域调用，无需额外配置
- `thumbnail`/`image_url` 是相对路径（如 `/uploads/thumb_rec_xxx.jpg`），前端拼接后端域名即可访问图片
- 上传图片用 `multipart/form-data`，字段名固定为 `image`

## 常见问题

- **启动报错 "Missing Gemini API key"**：检查 `.env.local` 是否存在、`GEMINI_API_KEY` 是否填写正确
- **调用 Gemini 超时或连接失败**：检查 `.env.local` 里 `PROXY_URL` 是否正确指向你本地代理软件的端口；如果不需要代理，删掉这一行
- **模型加载报警告 `MobileNetV2FeatureExtractor is deprecated`**：这是 `transformers` 新版本的提示信息，不影响功能，可以忽略


## 前后端连调-如何使用我们的项目

# 后端：完成后端所需环境配置后，终端输入
python -m uvicorn app.main:app --reload --port 8000
确认后端接口正常

# 前端：新建一个终端
cd frontend/plant-diagnosis
npm run dev

网页端可直接访问http://localhost:3000
手机端可在连接同一网络情况下直接访问http://172.20.10.3:3000

# 如果需要转化公网访问
新开一个窗口
ngrok http 3000

手机浏览器访问https://jet-spleen-cyclic.ngrok-free.dev（注意：ngrok可能变更网页地址，具体哪个网页看终端中显示的地址
“Forwarding                    https://jet-spleen-cyclic.ngrok-free.dev -> http://localhost:3000”

# 注：配置ngrok
npm install -g ngrok

在ngrok官网https://dashboard.ngrok.com/signup?utm_source=chatgpt.com 注册免费账号

终端输入ngrok config add-authtoken xxxxxxxxxxxxxxxxxxxx（你的api）

再运行ngrok http 3000即可

<img width="2168" height="1410" alt="屏幕截图 2026-06-07 183322" src="https://github.com/user-attachments/assets/01466f52-871a-4397-a407-ca4ad2737fdc" />
