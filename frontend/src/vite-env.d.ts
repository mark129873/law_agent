/// <reference types="vite/client" />
// 上面这行为 Vite 的内置能力提供 TypeScript 类型声明（Vite 脚手架的标准文件）：
// 1. 让 `import './index.css'` 这类样式导入通过类型检查；
// 2. 提供 import.meta.env 环境变量等 Vite 特有 API 的类型。
// 没有它，TS7 会在构建时对 CSS 导入报 TS2882 错误。
