// 应用路由表：集中定义「URL 路径 → 页面组件」的映射关系。
// 为什么集中放在一个文件：后续所有页面都在这一个文件里登记，
// 只看这里就能了解全部页面结构，避免路由定义散落各处。
// 当前单页应用：根路径渲染应用外壳（侧边栏 + 主区域），视图切换在壳内完成。
import { Routes, Route } from 'react-router-dom'
import AppShell from './components/AppShell'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />} />
    </Routes>
  )
}
