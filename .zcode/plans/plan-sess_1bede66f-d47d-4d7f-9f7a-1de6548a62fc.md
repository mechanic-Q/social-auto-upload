## 修复头条发布：标题丢失 + 发布判定总失败

### 根因回顾
1. 标题/话题选择器对当前西瓜上传通道页面失配，标题填错位置且无回读、无日志，完全静默
2. `submit_publish` 用旧 URL pattern（`graphic/publish/manage`）判成功，实际管理页已是 `manage/content/all`，发布成功也被报失败
3. 点发布超时后盲点页面最后一个"确认/确定"按钮，可能替用户确认空标题发布
4. `submit_publish` 异常只进 CLI stderr 不进 toutiao.log，日志"看起来正常"
5. 附带：cookie 校验 goto 超时被误判失效；skill 文档 30 字上限与代码 300 字不一致

### 第一步：无头实测取证（不发布、不花钱）
写一个一次性探测脚本（复用现有 cookie `cookies/toutiao_diyi.json`）：
- 打开 `profile_v4/xigua/upload-video`，dump 页面所有 input/textarea 的 placeholder、class、可见性 → 确定标题框/简介框/话题框真实定位
- 检查 `profile_v4/manage/content/all` 与 `graphic/publish/manage` 哪个是发布后真实跳转地址（从后台内容管理入口实测）
- 产出：选择器实测清单 + 截图存 `/tmp/`

### 第二步：修 `uploader/toutiao_uploader/main.py`
1. **fill_title_description_and_tags**
   - 按第一步实测结果更新标题/简介/话题选择器，收窄 fallback（不允许泛匹配 `.first` 碰运气）
   - 填标题后 `input_value()` 回读校验，不一致重试 2 次，仍失败则抛错终止（绝不静默发出无标题视频）
   - 标题填入前后加日志（当前该步骤零日志）
   - 标题填入挪到 `wait_for_upload_complete` 之后执行，避免表单初始化竞争
2. **submit_publish**
   - URL 成功判定按实测放宽（匹配真实管理页，新旧 pattern 兼容）
   - 删除确认弹窗"盲点 `.last`"：点之前检查弹窗文案，若含"标题"等警告字样则截图并抛错终止；正常确认弹窗才点
   - 每步加日志；失败路径 `toutiao_logger.error` + 截图到 `/tmp/toutiao_submit_fail.png`（失败必须进日志）
3. **cookie_auth**：goto 超时重试 1 次再判失效，不再把网络慢当 cookie 失效

### 第三步：修正 skill 文档口径
- `sau_cli.py` help 文本、`skills/toutiao-upload/references/troubleshooting.md` 中"标题 ≤30 字"改为与代码一致的 300 字（troubleshooting 同时补"发布失败先看 toutiao.log error"指引）

### 第四步：验证
1. 单元层：跑现有 `tests/test_sau_toutiao_cli.py` 确认 CLI 契约不破
2. 端到端：用 `--draft` 存草稿模式跑一次真实上传（草稿不对外发布，安全），验证标题回读、封面、声明、草稿保存成功；日志中应出现新的标题校验日志行
3. 草稿验证通过后，真实发布由用户确认时机（发布是外发动作，不自动执行）
4. 顺带核验话题联想选择器修复后能命中候选

### 不做的事
- 不动 collector/generic.py 未提交改动（与本问题无关，保持原样由用户决定是否提交）
- 不改其他平台上传器