// 应用路由表：集中定义「URL 路径 → 页面组件」的映射关系。
// 为什么集中放在一个文件：后续会话页、知识库页陆续加入时，
// 只看这一个文件就能了解全部页面结构，避免路由定义散落各处。
// 当前是 FE-001 基础框架，只注册首页；对话页（FE-004）、知识库页（FE-008）完成后在此登记。
import { Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'

export default function App() {
  return (
    <Routes>
      {/* 首页：FE-003（应用 Shell）/ FE-004（对话页面）完成后将替换为真实布局 */}
      <Route path="/" element={<HomePage />} />
    </Routes>
  )
}
