# Agent 动态编写计算代码 + 部署 API 端点 - 实施方案

**文档版本**: v1.0  
**日期**: 2026-06-11  
**目标**: 为 U-Chrom webapp 实现 agent 自主完成 "算法设计 → 数据计算 → 端点部署 → 可视化" 全链路  
**基线代码**: `.claude/worktrees/webapp/webapp/` @ `43cfb549c` (`feat/phase0-viewer-integration`)

---

## 一、架构设计（已确定）

### 推荐方案：混合模式
- **安全层**: AST 白名单验证 + 替换 `__builtins__` + 禁止 dunder 属性
- **执行模式**: 代码生成 + 受限 exec，运行时动态注册 FastAPI 路由（无需重启）
- **数据访问**: 复用全局 ChromData (`current_session.chromdata`)
- **端点格式**: 统一 JSON data type (`/api/custom/{id}/{chrom}?format=gosling`)
- **超时机制**: `concurrent.futures.ThreadPoolExecutor` (不能用 `signal.alarm`，见技术发现)
- **适用边界**: 小数据 (<100K spots) + O(n) 简单分析 + 10s 超时；大数据/MDS 仍走预编译

### 工作流
```
Agent → write_analysis_function tool
  ↓
代码生成 (Claude API, 3-15秒)
  ↓
安全检查 (AST 白名单 + 静态分析)
  ↓
动态注册 FastAPI 端点 (/api/custom/{id}/{chrom})
  ↓
返回 data_url + render handle → render_gosling
```

---

## 二、关键技术发现（来自真实代码）

### 1. 为什么不能用 `signal.alarm`
- **agent loop** 运行在 `uvicorn` 的 event-loop 线程 (`ws_handler.py:107`)
- **REST 端点** 运行在 FastAPI 的 threadpool（非主线程）
- `signal.signal` 只能在**主线程**注册，会抛 `ValueError: signal only works in main thread`
- **必须使用** `concurrent.futures.ThreadPoolExecutor.submit().result(timeout=...)`

### 2. 通配路由优于运行时 `add_api_route`
- 运行时 `app.add_api_route` 在多 worker / OpenAPI schema 重建时有**竞态和内存泄漏**
- FastAPI **不支持安全地删除路由**
- **推荐**: 一个 `{analysis_id}` 参数路由 + 内存 dict 查表，即可"运行时部署、无需重启"

### 3. ChromData 访问契约
- 全局访问: `data_api.current_session.chromdata` (`data_api.py:15`)
- 标准取数: `_cd_or_404()` (`strc_api.py:29`)
- 可用方法: `cd.get_chrom(chrom)`, `cd.compute_distances(trace_id=...)`, 属性 `cd.coords / cd.spots / cd.cells`

### 4. 端点返回契约
- 复用 `_respond(key, records, fmt)` (`strc_api.py:79`)
- 复用 `_df_to_records` (`strc_api.py:69`) 处理 NaN→None
- 返回格式: `format=gosling` → 裸数组; 否则 `{key: [...]}`

---

## 三、新增文件设计

### 3.1 `webapp/backend/dynamic_analysis.py`
**职责**: 沙箱（AST 验证 + 编译 + 受限执行）

**核心安全机制**:
```python
# 1. 禁止的节点类型
FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom,         # 函数体内禁止 import
    ast.Global, ast.Nonlocal,           # 禁止作用域逃逸
    ast.With, ast.AsyncWith,            # 禁止上下文管理器 (open, locks)
    ast.AsyncFunctionDef, ast.Await,    # 禁止 async
    ast.Lambda,                         # 保持可分析性
)

# 2. 禁止的名称
FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "compile", "open", "input", "__import__",
    "globals", "locals", "vars", "dir", "getattr", "setattr",
    ...
})

# 3. 禁止所有 dunder 属性访问（封死逃逸链）
FORBIDDEN_ATTR_SUBSTR = ("__",)

# 4. 替换 __builtins__（最硬的防线）
SAFE_BUILTINS = {
    "len", "range", "enumerate", "zip", "min", "max", "sum", 
    "abs", "round", "sorted", "list", "dict", "set", "tuple",
    "float", "int", "str", "bool", "map", "filter", "any", "all",
    # 注意: 无 __import__, 无 open, 无 getattr
}

# 5. 预绑定模块（无需 import）
ALLOWED_MODULES = {"np": np, "pd": pd}
```

**关键类**:
```python
class CompiledAnalysis:
    name: str                       # 注册 id
    source: str                     # 源代码
    fn: Callable                    # analyze(cd, chrom, **params) -> pd.DataFrame
    chromosome_field: str = "chrom"
    genomic_fields: tuple = ("start", "end")
    suggested_mark: str = "rule"
    result_key: str = "records"

def compile_analysis(name: str, source: str, **meta) -> CompiledAnalysis:
    """验证 + 编译 + 绑定到受限命名空间"""
    tree = validate_source(source)  # AST 白名单检查
    code = compile(tree, filename=f"<analysis:{name}>", mode="exec")
    
    sandbox_globals = {
        "__builtins__": SAFE_BUILTINS,   # 替换 builtins
        **ALLOWED_MODULES,               # np, pd 预绑定
    }
    exec(code, sandbox_globals, sandbox_locals)
    return CompiledAnalysis(name=name, fn=sandbox_locals["analyze"], ...)

def run_with_timeout(compiled: CompiledAnalysis, cd, chrom: str,
                     params: dict, timeout_s: float = 10.0) -> pd.DataFrame:
    """使用 ThreadPoolExecutor 实现超时"""
    fut = _POOL.submit(compiled.fn, cd, chrom, **(params or {}))
    result = fut.result(timeout=timeout_s)  # 抛 TimeoutError
    if not isinstance(result, pd.DataFrame):
        raise TypeError("analyze() must return pandas DataFrame")
    return result
```

**强制签名**:
```python
def analyze(cd, chrom, **params):
    # cd: ChromData 已 subset 到 chrom
    # 可用: cd.coords, cd.spots, cd.compute_distances(trace_id=...)
    # 预绑定: np, pd（无需 import）
    # 必须返回 DataFrame，包含 chromosome_field 和 genomic_fields
    ...
    return pd.DataFrame({"chrom": [...], "start": [...], "end": [...], ...})
```

---

### 3.2 `webapp/backend/dynamic_api.py`
**职责**: 动态注册表 + 运行时路由

**关键设计**:
```python
dynamic_router = APIRouter()

# 内存注册表（单用户，重启丢失）
_REGISTRY: dict[str, CompiledAnalysis] = {}

def register_analysis(name: str, source: str, **meta) -> dict:
    """验证+编译+存储，返回 render handle"""
    compiled = compile_analysis(name, source, **meta)
    _REGISTRY[name] = compiled
    return render_handle(compiled)

def render_handle(c: CompiledAnalysis, chrom: str = "{chrom}") -> dict:
    """返回与 run_analysis 相同格式的 handle"""
    return {
        "analysis_id": c.name,
        "data_url": f"/api/custom/{c.name}/{chrom}?format=gosling",
        "chromosome_field": c.chromosome_field,
        "genomic_fields": list(c.genomic_fields),
        "suggested_mark": c.suggested_mark,
    }

@dynamic_router.get("/api/custom/{analysis_id}/{chrom}")
def run_custom(analysis_id: str, chrom: str, format: Optional[str] = None):
    """通配端点：查表执行，复用 strc_api 契约"""
    compiled = _REGISTRY.get(analysis_id)
    if compiled is None:
        raise HTTPException(404, detail={"error": f"No analysis '{analysis_id}'"})
    
    cd = _cd_or_404()
    sub = cd.get_chrom(chrom)
    
    # 适用边界检查
    if sub.coords.shape[0] > 100_000:
        raise HTTPException(413, detail={"error": "Region too large (>100K spots)"})
    
    # 执行（带超时）
    try:
        df = run_with_timeout(compiled, cd, chrom, params={}, timeout_s=10.0)
    except TimeoutError as e:
        raise HTTPException(504, detail={"error": str(e)})
    
    # 复用 strc_api 的响应格式
    return _respond(compiled.result_key, _df_to_records(df), format)
```

---

## 四、现有文件改动点（精确到 file:line）

### 4.1 `agent_tools.py`

**位置 1**: 在 `run_analysis` 之后、`export_view` 之前插入新 tool (约 `agent_tools.py:216`)

```python
{
    "name": "write_analysis_function",
    "description": """Author and deploy a CUSTOM Python analysis as a live API endpoint.

Use this when no built-in analysis (run_analysis: tad/loop/compartment) fits —
e.g. custom insulation score, radius-of-gyration profile, or bespoke TAD caller.

YOUR CODE MUST define exactly:
    def analyze(cd, chrom, **params):
        # cd: ChromData already subset to `chrom`
        # available: cd.coords (N,3), cd.spots (DataFrame), 
        #            cd.compute_distances(trace_id=...)
        # pre-bound: np, pd (NO imports allowed)
        # MUST return DataFrame with chromosome_field and genomic_fields
        ...
        return pd.DataFrame({"chrom": [...], "start": [...], "end": [...]})

FORBIDDEN: import, open, eval/exec, file/network/os access, dunder attributes.

After success, returns SAME render handle as run_analysis (data_url / 
chromosome_field / genomic_fields / suggested_mark). Then call render_gosling 
with a json track pointing at data_url.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "short id (a-z0-9_)"},
            "code": {"type": "string", "description": "Python defining analyze()"},
            "chromosome_field": {"type": "string", "description": "chrom column (default 'chrom')"},
            "genomic_fields": {"type": "array", "items": {"type": "string"},
                               "description": "position columns, e.g. ['start','end']"},
            "suggested_mark": {"type": "string",
                               "description": "Gosling mark: rule/bar/link/point/line"},
        },
        "required": ["name", "code"],
    },
},
```

**位置 2**: 在工具清单 (约 `agent_tools.py:240`) 添加一行

```python
- write_analysis_function → author+deploy a CUSTOM sandboxed analysis as live endpoint, then render its output
```

**位置 3**: SYSTEM_PROMPT 末尾追加

```python
When a user asks for an analysis that tad/loop/compartment don't cover, prefer
write_analysis_function over add_notebook_cell: it deploys a reusable endpoint
you can immediately visualize. Define analyze(cd, chrom, **params) returning a
DataFrame; you cannot import modules (np/pd are pre-bound) or touch filesystem/
network. Keep it O(n) over <100K spots.
```

---

### 4.2 `ws_handler.py`

**位置**: `run_analysis` 分支结束后 (约 `ws_handler.py:306`)，`select_cells` 之前

```python
elif tool_use.name == "write_analysis_function":
    name = (tool_use.input.get("name") or "").strip()
    code = tool_use.input.get("code", "")
    meta = {}
    if tool_use.input.get("chromosome_field"):
        meta["chromosome_field"] = tool_use.input["chromosome_field"]
    if tool_use.input.get("genomic_fields"):
        meta["genomic_fields"] = tuple(tool_use.input["genomic_fields"])
    if tool_use.input.get("suggested_mark"):
        meta["suggested_mark"] = tool_use.input["suggested_mark"]
    if tool_use.input.get("name"):
        meta["result_key"] = name

    try:
        from .dynamic_api import register_analysis
        from .dynamic_analysis import AnalysisValidationError
        try:
            handle = register_analysis(name, code, **meta)
        except AnalysisValidationError as ve:
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps({
                    "success": False,
                    "error": f"Rejected by sandbox: {ve}",
                    "hint": "Remove imports/IO/dunder access; define analyze(cd, chrom, **params) returning DataFrame.",
                }),
            })
        else:
            # 通知前端新分析已部署（可选）
            await websocket.send_json({
                "type": "agent_artifact",
                "artifact_type": "custom_analysis_deployed",
                "analysis_id": name,
                "data_url": handle["data_url"],
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps({
                    "success": True,
                    "analysis_id": name,
                    "data_url": handle["data_url"],
                    "chromosome_field": handle["chromosome_field"],
                    "genomic_fields": handle["genomic_fields"],
                    "suggested_mark": handle["suggested_mark"],
                    "next_step": (
                        "Endpoint deployed. Replace {chrom} in data_url with real "
                        "chromosome, then call render_gosling with data="
                        "{\"type\":\"json\",\"url\":<data_url>,"
                        "\"chromosomeField\":chromosome_field,"
                        "\"genomicFields\":genomic_fields} and mark=suggested_mark."
                    ),
                }),
            })
    except Exception as e:
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": f"Deploy failed: {str(e)}",
        })
```

---

### 4.3 `main.py`

**位置**: `app.include_router(strc_router)` 之后 (约 `main.py:32`)

```python
from .dynamic_api import dynamic_router
app.include_router(dynamic_router)
```

---

## 五、测试方案

### 5.1 单元测试: `tests/test_dynamic_analysis.py`

```python
import pandas as pd, pytest
from webapp.backend.dynamic_analysis import (
    compile_analysis, validate_source, run_with_timeout, AnalysisValidationError)

GOOD_CODE = '''
def analyze(cd, chrom, **params):
    n = cd.coords.shape[0]
    starts = cd.spots["start"].to_numpy()
    return pd.DataFrame({"chrom": [chrom]*n, "start": starts, "end": starts+1})
'''

@pytest.mark.parametrize("src", [
    "import os\ndef analyze(cd, chrom, **p):\n    return pd",          # import
    "def analyze(cd, chrom, **p):\n    open('/etc/passwd')",          # open
    "def analyze(cd, chrom, **p):\n    return ().__class__.__bases__", # dunder
    "def analyze(cd, chrom, **p):\n    eval('1')",                    # eval
    "def f(): pass",                                                  # no analyze()
])
def test_malicious_rejected(src):
    with pytest.raises(AnalysisValidationError):
        validate_source(src)

def test_good_compiles_and_runs():
    # 使用 mock ChromData
    ...

def test_timeout():
    # 死循环应触发 TimeoutError
    ...

def test_non_dataframe_return_rejected():
    # 返回非 DataFrame 应报错
    ...
```

### 5.2 端点测试: `tests/test_dynamic_api.py`

复刻 `test_strc_api.py` 的 `TestClient` + mock ChromData 模式:
- `test_register_then_get_returns_records`
- `test_format_gosling_bare_array`
- `test_unknown_id_404`
- `test_region_too_large_413`
- `test_no_data_404`

### 5.3 Agent 集成测试: `tests/test_agent_linkage_tools.py` 扩展

```python
def test_write_analysis_deploys_and_returns_handle():
    # 复用现有 _run harness + mock Anthropic client
    # 验证 tool_result 含 data_url + render handle
    ...

def test_write_analysis_rejects_malicious():
    # import os 代码应返回 success: false
    ...
```

### 5.4 E2E: `tests/test_e2e_dynamic_custom.py`

- 真实 ChromData 小切片
- Agent 写自定义 TAD caller（基于 `cd.compute_distances` 的 directionality）
- `write_analysis_function` 部署
- `GET /api/custom/<id>/<chrom>?format=gosling` 拿到非空裸数组
- `render_gosling` artifact 发出
- 验收: record_count>0，artifact 包含 `custom_analysis_deployed` + `gosling_spec`

---

## 六、分阶段实施

### Phase 1: MVP（~3 天）

**交付物**:
- `dynamic_analysis.py` (纯 AST + 受限 builtins + 线程超时)
- `dynamic_api.py` (内存注册表 + 通配路由)
- §4 三处集成改动
- `test_dynamic_analysis.py` + `test_dynamic_api.py` + linkage 测试扩展

**验收标准**:
- ✅ 全部新单测通过
- ✅ 恶意样本（import/open/eval/dunder/无 analyze）100% 被拦
- ✅ 合法函数部署后端点返回 Gosling 裸数组
- ✅ E2E 自定义 TAD caller 跑通且 `render_gosling` 成功

---

### Phase 2: 加固（~2 天）

**改进项**:
- 引入 `RestrictedPython` (加进 `pyproject.toml`)
- `compile_analysis` 切到 `compile_restricted` + `safe_globals`/`limited_builtins`
- 内存限制：改用 `ProcessPoolExecutor`（可 `resource.setrlimit(RLIMIT_AS)` 在子进程）
- 注册表加上限（最多 50 个）、`name` 正则校验 `^[a-z0-9_]{1,32}$`

**验收标准**:
- ✅ 超时函数被进程级 kill
- ✅ `setrlimit` 触发的 MemoryError 被捕获返回 500
- ✅ RestrictedPython 拒绝属性写入

---

### Phase 3: 生产（可选，~1 周）

**改进项**:
- 容器/子解释器隔离（gVisor / nsjail）
- 网络/文件系统命名空间隔离
- 持久化注册表（落盘 + 启动重编译 + 审计日志）

**验收标准**:
- ✅ 逃逸测试套件（已知 CPython 沙箱 CVE 样本）在容器内无法访问宿主 FS/网络

---

## 七、边界与风险（含降级策略）

| 风险 | 影响 | 缓解 |
|------|------|------|
| **多线程超时不可硬杀** | 超时后线程继续跑，极端情况累积占 CPU | MVP 限 `max_workers=2` + 文档标注"信任环境"；加固阶段换 ProcessPool 真杀 |
| **ChromData 并发** | agent 代码若对 `cd.spots` 原地修改 | 在 `run_custom` 里传 `cd.get_chrom(chrom)` 副本，system prompt 明确"只读" |
| **阻塞 event loop** | 同步调 executor | `write_analysis_function` 只做编译（快）；真正执行在 REST 端点（FastAPI threadpool），双层隔离 |
| **生成代码质量** | 非 DataFrame、列名不符、空结果 | `run_with_timeout` 校验 DataFrame 类型；`_df_to_records` 容 NaN；`next_step` 提示 agent 自查 |
| **大数据/MDS** | 计算密集 | 硬限 100K spots (413) + 10s 超时；大计算仍走预编译 |
| **重启丢失** | 注册表纯内存 | 单用户 Phase 1 设计；需持久化时进生产阶段 |

---

## 八、成本估算

### Claude API 成本
- 输入: 系统提示词(2K) + 用户 prompt(0.5K) + schema(1K) = **3.5K tokens**
- 输出: Python 函数代码 = **0.5-2K tokens**
- 单次成本 (Opus): $0.015/1K input + $0.075/1K output ≈ **$0.05-0.15/次**
- 缓存命中率 60% → 每天 1000 次请求 → **$20-60/天**

### 开发成本
- MVP: 3 天
- 加固: 2 天
- 生产: 1 周（可选）
- 维护: +1 人周/月（安全审计 + 代码审查）

---

## 九、与现有架构的契合点

严格复刻现有契约：
- `ANALYSIS_REGISTRY` / `run_registered_analysis` 模式
- `_respond` / `_df_to_records` 响应格式
- `run_analysis` 的 render-handle 返回结构

Agent 的 "分析→渲染" 链路 (`render_gosling` json track) **零改动**即可消费自定义端点输出。

---

## 十、下一步行动

1. Review 本方案，确认技术决策
2. 创建 feature branch (`feat/dynamic-codegen-mvp`)
3. 实施 Phase 1 MVP (3 天)
4. E2E 验证后决定是否进入 Phase 2
