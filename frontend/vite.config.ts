// Vite 配置文件：定义前端项目的构建插件与开发服务器行为。
// 做了什么：
// 1. 注册 React 插件，让 Vite 能编译 JSX 并支持热更新（改代码浏览器自动刷新）；
// 2. 注册 Tailwind CSS v4 官方插件，由它扫描源码按需生成样式；
// 3. 配置开发代理：把 /api 开头的请求转发到后端 FastAPI（127.0.0.1:8000）。
// 为什么这么做：
// - 前端代码统一请求相对路径 /api/...，开发期由 Vite 转发，天然规避跨域（CORS）问题；
// - 后端 CORS 当前为 allow_origins=["*"]（开发态），走代理后生产收敛也不影响前端代码。
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173, // 固定开发端口，方便与文档、后端联调约定保持一致
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
