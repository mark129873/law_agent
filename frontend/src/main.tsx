// 应用入口文件：浏览器加载 index.html 后执行的第一段前端代码。
// 做了三件事：
// 1. 引入全局样式 index.css（Tailwind CSS 从这里生效）；
// 2. 用 BrowserRouter 包裹 App，启用前端路由（切换页面时不刷新整页）；
// 3. 把 App 渲染到 index.html 里的 <div id="root"> 上。
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

// StrictMode：React 的开发辅助模式（只在开发环境生效），
// 会故意把组件多渲染一次，帮助提前暴露副作用类问题；生产构建不受影响。
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
