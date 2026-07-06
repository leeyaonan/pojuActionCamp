import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from '@/components/Layout';

// 11 个页面（空桩）
import Home from '@/pages/Home';
import CreateCamp from '@/pages/CreateCamp';
import StudentDashboard from '@/pages/student/Dashboard';
import StudentRoute from '@/pages/student/Route';
import StudentCheckin from '@/pages/student/Checkin';
import VolunteerDashboard from '@/pages/volunteer/Dashboard';
import VolunteerGrading from '@/pages/volunteer/Grading';
import VolunteerArchive from '@/pages/volunteer/Archive';
import Manual from '@/pages/Manual';
import Scoring from '@/pages/Scoring';
import Settings from '@/pages/Settings';
import LLMSettings from '@/pages/LLMSettings';

/**
 * App 根组件：路由表，对齐技术方案 12.1。
 *
 * - 路由由 Layout 包裹：左侧边栏 + 主内容区。
 * - 学员营子路由守卫：/camp/:id/student/* 仅在 camp.role==='student' 时可访问。
 * - 志愿者营子路由守卫：/camp/:id/volunteer/* 仅在 camp.role==='volunteer' 时可访问。
 *   （守卫实现见 Layout 内的 RoleGuard 子组件。）
 */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/create" element={<CreateCamp />} />

        {/* 学员营 */}
        <Route path="/camp/:id/student" element={<StudentDashboard />} />
        <Route path="/camp/:id/student/route" element={<StudentRoute />} />
        <Route path="/camp/:id/student/checkin" element={<StudentCheckin />} />

        {/* 志愿者营 */}
        <Route path="/camp/:id/volunteer" element={<VolunteerDashboard />} />
        <Route path="/camp/:id/volunteer/grade" element={<VolunteerGrading />} />
        <Route path="/camp/:id/volunteer/archive/:studentId" element={<VolunteerArchive />} />

        {/* 全局 */}
        <Route path="/camp/:id/manual" element={<Manual />} />
        <Route path="/scoring" element={<Scoring />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/llm-settings" element={<LLMSettings />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}