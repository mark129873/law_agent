# init.md -- 开始工作前，请验证项目可以正常无报错构建。

在克隆仓库后或恢复开发工作时执行此验证：
- 如果存在后端项目, 验证后端项目可以正常构建与运行
- 如果存在前端项目, 验证前端项目可以正常构建与运行

- 检测AGENTS.md, progress.md, feature_list.json, clean-state-checklist.md, session-handoff.md 是否存在
- 检测docs/ARCHITECTURE.md, docs/PRODUCT.md, docs/RELIABILITY.md 是否存在
-  如果上述文件均存在, 则 echo "=== Init完成. 所有检查通过. ==="
-  如果上述文件中存在缺失, 则 echo "=== Init完成. 有缺失文件. ==="
