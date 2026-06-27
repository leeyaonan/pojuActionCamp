import { useMemo } from 'react';
import { Layout as AntLayout, Menu, Button, Spin, Empty } from 'antd';
import {
  PlusOutlined,
  AppstoreOutlined,
  SettingOutlined,
  ApiOutlined,
  StarOutlined,
  UserOutlined,
  TeamOutlined,
  CalendarOutlined,
  ReadOutlined,
  EditOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Link, Outlet, useLocation, useParams } from 'react-router-dom';
import { useCamps } from '@/hooks/useCamps';
import type { CampStatus } from '@/api/types';

const { Sider, Content, Header } = AntLayout;

/**
 * 全局布局：
 * - 侧边栏 (248px)：Logo + 新建按钮 + 行动营分组 + 全局设置。
 * - 主内容：顶部页头 slot + Outlet。
 *
 * 侧边栏分组规则：
 * - 行动营按 role 分组：学员营 / 志愿者营。
 * - 每组展开后展示该营的子路由（学员:今日看板/学习路线/打卡/手册；志愿者:学员看板/作业评改/手册）。
 * - 全局区始终展示：评分标准、接口配置。
 */
export default function Layout() {
  const location = useLocation();
  const params = useParams();
  const { data: camps, isLoading } = useCamps();

  // 行动营分组
  const grouped = useMemo(() => {
    const studentCamps = (camps ?? []).filter((c) => c.role === 'student');
    const volunteerCamps = (camps ?? []).filter((c) => c.role === 'volunteer');
    return { studentCamps, volunteerCamps };
  }, [camps]);

  // 当前激活菜单项（按当前路由推断）
  const selectedKey = location.pathname;

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        width={248}
        style={{
          background: 'var(--surface)',
          borderRight: '1px solid var(--border)',
          overflow: 'auto',
        }}
      >
        {/* Logo */}
        <div
          style={{
            padding: '20px 20px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: 'var(--primary)',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
            }}
          >
            AI
          </div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>破局行动营</div>
        </div>

        {/* 新建按钮 */}
        <div style={{ padding: '12px 16px' }}>
          <Link to="/create">
            <Button type="primary" icon={<PlusOutlined />} block>
              新建行动营
            </Button>
          </Link>
        </div>

        {/* 分组菜单 */}
        {isLoading ? (
          <div style={{ padding: 24, textAlign: 'center' }}>
            <Spin />
          </div>
        ) : (
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            style={{ border: 'none', background: 'transparent' }}
            items={buildMenuItems(grouped.studentCamps, grouped.volunteerCamps)}
          />
        )}
      </Sider>

      <AntLayout style={{ background: 'var(--bg)' }}>
        <Header
          style={{
            background: 'var(--surface)',
            padding: '0 24px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ fontSize: 13, color: 'var(--text-sub)' }}>
            {/* 当前路径面包屑占位 */}
            <BreadcrumbHint pathname={location.pathname} params={params} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-light)' }}>MVP 本地工具</div>
        </Header>
        <Content>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}

function BreadcrumbHint({
  pathname,
  params,
}: {
  pathname: string;
  params: Record<string, string | undefined>;
}) {
  if (pathname === '/') return <>行动营列表</>;
  if (pathname === '/create') return <>创建行动营</>;
  if (pathname.startsWith('/camp/') && params.id) {
    const campLabel = `营 #${params.id}`;
    if (pathname.endsWith('/student')) return <>{campLabel} · 学员 · 今日看板</>;
    if (pathname.endsWith('/student/route')) return <>{campLabel} · 学员 · 学习路线</>;
    if (pathname.endsWith('/student/checkin')) return <>{campLabel} · 学员 · 打卡生成</>;
    if (pathname.endsWith('/volunteer')) return <>{campLabel} · 志愿者 · 学员看板</>;
    if (pathname.endsWith('/volunteer/grade')) return <>{campLabel} · 志愿者 · 作业评改</>;
    if (pathname.includes('/volunteer/archive/')) return <>{campLabel} · 志愿者 · 学员档案</>;
    if (pathname.endsWith('/manual')) return <>{campLabel} · 手册管理</>;
  }
  if (pathname === '/scoring') return <>评分标准</>;
  if (pathname === '/settings') return <>接口配置</>;
  return null;
}

/**
 * 构造侧边栏菜单 items（按 design.md P1 列表 + 分组）。
 */
function buildMenuItems(
  studentCamps: Array<{ id: number; name: string; status: CampStatus }>,
  volunteerCamps: Array<{ id: number; name: string; status: CampStatus }>
) {
  const studentSubmenu =
    studentCamps.length === 0
      ? [
          {
            key: 'student-empty',
            icon: <UserOutlined />,
            label: <span style={{ color: 'var(--text-light)' }}>暂无学员营</span>,
            disabled: true,
          },
        ]
      : studentCamps.flatMap((c) => [
          {
            key: `student-${c.id}`,
            icon: <UserOutlined />,
            label: c.name,
            type: 'group' as const,
            children: [
              {
                key: `/camp/${c.id}/student`,
                icon: <AppstoreOutlined />,
                label: <Link to={`/camp/${c.id}/student`}>今日看板</Link>,
              },
              {
                key: `/camp/${c.id}/student/route`,
                icon: <CalendarOutlined />,
                label: <Link to={`/camp/${c.id}/student/route`}>学习路线</Link>,
              },
              {
                key: `/camp/${c.id}/student/checkin`,
                icon: <EditOutlined />,
                label: <Link to={`/camp/${c.id}/student/checkin`}>打卡</Link>,
              },
              {
                key: `/camp/${c.id}/manual`,
                icon: <ReadOutlined />,
                label: <Link to={`/camp/${c.id}/manual`}>手册</Link>,
              },
            ],
          },
        ]);

  const volunteerSubmenu =
    volunteerCamps.length === 0
      ? [
          {
            key: 'volunteer-empty',
            icon: <TeamOutlined />,
            label: <span style={{ color: 'var(--text-light)' }}>暂无志愿者营</span>,
            disabled: true,
          },
        ]
      : volunteerCamps.flatMap((c) => [
          {
            key: `volunteer-${c.id}`,
            icon: <TeamOutlined />,
            label: c.name,
            type: 'group' as const,
            children: [
              {
                key: `/camp/${c.id}/volunteer`,
                icon: <AppstoreOutlined />,
                label: <Link to={`/camp/${c.id}/volunteer`}>学员看板</Link>,
              },
              {
                key: `/camp/${c.id}/volunteer/grade`,
                icon: <EditOutlined />,
                label: <Link to={`/camp/${c.id}/volunteer/grade`}>作业评改</Link>,
              },
              {
                key: `/camp/${c.id}/manual`,
                icon: <ReadOutlined />,
                label: <Link to={`/camp/${c.id}/manual`}>手册</Link>,
              },
            ],
          },
        ]);

  return [
    {
      key: 'student-group',
      icon: <UserOutlined />,
      label: '学员营',
      type: 'group' as const,
      children: studentSubmenu,
    },
    {
      key: 'volunteer-group',
      icon: <TeamOutlined />,
      label: '志愿者营',
      type: 'group' as const,
      children: volunteerSubmenu,
    },
    { type: 'divider' as const },
    {
      key: '/',
      icon: <AppstoreOutlined />,
      label: <Link to="/">全部行动营</Link>,
    },
    {
      key: '/scoring',
      icon: <StarOutlined />,
      label: <Link to="/scoring">评分标准</Link>,
    },
    {
      key: '/settings',
      icon: <ApiOutlined />,
      label: <Link to="/settings">接口配置</Link>,
    },
  ];
}

// 占位导出，避免 TypeScript noUnusedLocals 警告（保留供后续页面使用）
export { Empty, ThunderboltOutlined, SettingOutlined };