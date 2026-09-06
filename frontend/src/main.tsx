// 应用入口文件：浏览器加载 index.html 后执行的第一段前端代码。
// 结构（从外到内）：BrowserRouter（前端路由）> AppProvider（全局状态）> App（路由表）。
// 顺序原因：路由渲染出的页面组件要用 useAppStore() 读全局状态，
// 所以 Provider 必须包在路由外面，否则页面拿不到状态。
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AppProvider } from './state/AppContext'
import App from './App'
import './index.css'

// StrictMode：React 的开发辅助模式（只在开发环境生效），
// 会故意把组件多渲染一次，帮助提前暴露副作用类问题；生产构建不受影响。
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </StrictMode>,
)
