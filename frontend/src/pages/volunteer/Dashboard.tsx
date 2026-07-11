import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Button,
  Spin,
  Empty,
  Tabs,
  Input,
  Table,
  Tag,
  Tooltip,
  Modal,
  App as AntApp,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  SyncOutlined,
  SearchOutlined,
  EditOutlined,
  FileTextOutlined,
  TeamOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useCamp } from '@/hooks/useCamps';
import {
  useStudents,
  useSyncBoard,
  usePendingGrades,
  useInitArchive,
  useRefreshArchive,
  useReminders,
} from '@/hooks/useVolunteer';
import DeleteCampButton from '@/components/DeleteCampButton';
import type {
  InitResult,
  PendingGradeOut,
  ReminderItem,
  StudentStatus,
  StudentSummary,
} from '@/api/types';

/**
 * P6 志愿者·学员看板（design.md 6.P6 + ui-prototype #volunteer-dashboard）。
 *
 * 页面结构：
 * 1. 页头：标题「学员看板」+ 志愿者徽章 + 营名 + 上次同步时间 +
 *    「⏱ 定时同步」标签 + 「🔄 立即同步」主按钮。
 * 2. 统计 4 卡：带教学员 / 待评改（warn）/ 今日已打卡 / 打卡不足需提醒（danger）。
 * 3. Tab 行：全部 / 待评改 / 打卡不足 / 已评改（带数量徽章）+ 搜索框。
 * 4. 学员表格：昵称 / 已打卡 Day / 有效天数 / 距目标 / 最近星级 / 状态 / 操作。
 *
 * 数据源：
 * - useCamp(campId)         营基本信息（名称 / 起止 / 总天数）
 * - useStudents(campId, status) 学员列表（按 status 筛选；切 Tab 重查）
 * - usePendingGrades(campId) 待评改列表（用于统计「待评改」数量）
 * - useSyncBoard(campId)    手动同步 mutation（成功后 invalidate students）
 */
export default function VolunteerDashboard() {
  const params = useParams<{ id: string }>();
  const campId = params.id ? Number(params.id) : undefined;

  // 营详情（用于副标题与营名）
  const { data: camp, isLoading: campLoading } = useCamp(campId);
  // 待评改列表（每条 = 一条 CheckinRecord；营未开始时应为空）
  const { data: pendingGrades } = usePendingGrades(campId);

  // 当前 Tab：'all' | 'pending' | 'insufficient' | 'graded' | 'remind'
  //  - 'all'        → 全部学员（数据来自破局 member-clock-in-status 实时拉取）
  //  - 'pending'    → 真·待评改打卡列表（/grades/pending）
  //  - 'insufficient' → 本地 valid_days 不足（学员档案视角）
  //  - 'graded'     → 本地 valid_days 已达标（学员档案视角）
  //  - 'remind'     → 待提醒列表（数据来自破局 member-clock-in-status）
  const [tab, setTab] = useState<TabKey>('all');
  // 学员昵称搜索（前端过滤）
  const [searchText, setSearchText] = useState('');

  // 待评改 tab 不走学员列表——它是「按打卡记录」维度；其余 tab 走学员看板。
  // 'all' 与 'remind' tab 都用 useReminders（破局实时数据），不走 useStudents。
  const studentStatus = useMemo<StudentStatus | undefined>(() => {
    if (tab === 'all') return undefined; // 「全部」tab 改用 reminders 数据
    if (tab === 'pending') return undefined; // 待评改由 usePendingGrades 单独渲染
    if (tab === 'remind') return undefined; // 待提醒由 useReminders 单独渲染
    if (tab === 'insufficient') return 'unqualified';
    if (tab === 'graded') return 'qualified';
    return undefined;
  }, [tab]);

  const { data: students, isLoading: studentsLoading, refetch } = useStudents(
    campId,
    studentStatus
  );

  // 手动同步
  const syncMut = useSyncBoard(campId ?? -1);
  const { message, modal } = AntApp.useApp();

  // 初始化 / 刷新学员档案（拉破局 query-people）
  const initMut = useInitArchive(campId ?? -1);
  const refreshMut = useRefreshArchive(campId ?? -1);

  // 待提醒列表（破局实时拉取；用于「全部」与「待提醒」tab）
  const { data: reminders, isLoading: remindersLoading } = useReminders(campId);

  // 全部学员（用于 Tab 数量徽章 + 统计）
  const { data: allStudents } = useStudents(campId);

  // 五个 Tab 的数量：
  //  - all      → 破局 reminders 总数（破局视角的"全部"）
  //  - pending  → 真·待评改数（= pendingGrades 长度，营未开始为 0）
  //  - others   → 来自学员列表的 status 过滤
  //  - remind   → reminders 数量（破局视角的"待提醒"）
  const counts = useMemo(() => {
    const list = allStudents ?? [];
    return {
      all: (reminders ?? []).length,
      pending: (pendingGrades ?? []).length,
      insufficient: list.filter((s) => s.status === 'unqualified').length,
      graded: list.filter((s) => s.status === 'qualified').length,
      remind: (reminders ?? []).length,
    };
  }, [allStudents, pendingGrades, reminders]);

  // 今日已打卡近似 = 待评改列表数（它们都是已提交但未/刚评的）+ 历史已评改中
  // 今日的暂未通过其他接口拉，留作 MVP 简化（接口已存在 /grading_audit/today
  // 时可接入）。营未开始时 pendingGrades 为空 → 自然落到 0。
  const todayCheckedInCount = useMemo(
    () => (pendingGrades ?? []).length,
    [pendingGrades]
  );

  // 同步处理
  const handleSync = async () => {
    if (!campId) return;
    try {
      const res = await syncMut.mutateAsync();
      if (res.success) {
        message.success(res.message || '同步成功');
        refetch();
      } else {
        message.warning(res.message || '同步未完成');
      }
    } catch {
      // 错误已由 hook 内的 toastOnBizError 处理
    }
  };

  /**
   * 初始化 / 刷新学员档案入口。
   *
   * - mode='init'    → POST /archive/init
   * - mode='refresh' → POST /archive/refresh（覆盖式更新，不影响打卡记录）
   *
   * 弹 modal.confirm 二次确认；确认后调 mutation；成功调 showArchiveResult 展示明细。
   */
  const handleArchiveAction = (mode: 'init' | 'refresh') => {
    if (!campId) return;
    const isInit = mode === 'init';
    modal.confirm({
      title: isInit ? '初始化学员档案' : '刷新学员档案',
      content: isInit
        ? '将调用破局 query-people 按当前 actionId 拉取本期全部学员并写入本地档案。学员档案与打卡记录互不干扰，但本期一旦执行可重复点击"刷新"覆盖更新。'
        : '刷新将按 (camp, poju_student_id) 覆盖式更新本地扩展字段（昵称/微信/电话/打卡次数等）。不影响打卡记录与历史评改。',
      okText: isInit ? '确定初始化' : '确定刷新',
      cancelText: '取消',
      okButtonProps: {
        loading: isInit ? initMut.isPending : refreshMut.isPending,
      },
      onOk: async () => {
        try {
          const res = isInit
            ? await initMut.mutateAsync()
            : await refreshMut.mutateAsync();
          showArchiveResult(res, isInit ? '初始化完成' : '刷新完成');
          refetch();
        } catch {
          // 已由 hook 内 toastOnBizError 处理
        }
      },
    });
  };

  /** 将 InitResult 用 Modal.info 展示明细（含 errors 列表） */
  const showArchiveResult = (res: InitResult, title: string) => {
    const total = res.imported + res.updated;
    const summary = (
      <div style={{ lineHeight: 1.8 }}>
        <div>
          共处理 <strong>{total}</strong> 名学员
          （新增 <strong>{res.imported}</strong>，更新{' '}
          <strong>{res.updated}</strong>
          {res.skipped > 0 && (
            <>
              ，跳过 <strong>{res.skipped}</strong>
            </>
          )}
          ）
        </div>
        {res.total_from_poju > total && (
          <div style={{ color: 'var(--text-sub)', fontSize: 12 }}>
            破局接口总条数 {res.total_from_poju}，已遍历{' '}
            {res.pages_fetched} 页
          </div>
        )}
        {res.errors.length > 0 && (
          <div
            style={{
              marginTop: 10,
              padding: '8px 12px',
              borderRadius: 6,
              background: 'var(--warning-bg, #fef3c7)',
              color: '#92400e',
              fontSize: 12,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              以下分页失败（已跳过并继续翻页）：
            </div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {res.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
    Modal.info({
      title,
      content: summary,
      okText: '我知道了',
      width: 480,
    });
  };

  /**
   * 入页检查 sessionStorage 是否有"待初始化"标记。
   * CreateCamp 创建志愿者营（且填了 actionId）后会写入；这里消费并清理。
   * 仅在尚未初始化（students 为空）时弹，避免无意义打扰。
   */
  useEffect(() => {
    if (!campId) return;
    let pendingId: string | null = null;
    try {
      pendingId = sessionStorage.getItem('pending_init_camp_id');
    } catch {
      // 忽略
    }
    if (pendingId && pendingId === String(campId) && !studentsLoading) {
      try {
        sessionStorage.removeItem('pending_init_camp_id');
      } catch {
        // 忽略
      }
      const listEmpty = (allStudents?.length ?? 0) === 0;
      if (listEmpty) {
        // 用 setTimeout 推到下一个 tick，避免 Modal 与首次渲染抢焦点
        setTimeout(() => handleArchiveAction('init'), 100);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campId, studentsLoading, allStudents?.length]);

  // 搜索过滤后的学员列表
  const filteredStudents = useMemo(() => {
    if (!students) return [];
    const kw = searchText.trim().toLowerCase();
    if (!kw) return students;
    return students.filter(
      (s) => s.nickname.toLowerCase().includes(kw) || (s.wechat ?? '').toLowerCase().includes(kw)
    );
  }, [students, searchText]);

  // 待评改打卡列表的搜索过滤（学员昵称 / day_number）
  const filteredPendingGrades = useMemo(() => {
    const list = pendingGrades ?? [];
    const kw = searchText.trim().toLowerCase();
    if (!kw) return list;
    return list.filter(
      (p) =>
        p.student_nickname.toLowerCase().includes(kw) ||
        String(p.day_number).includes(kw)
    );
  }, [pendingGrades, searchText]);

  // 待提醒 / 全部 tab 的搜索过滤（学员昵称 / 编号）
  const filteredReminders = useMemo(() => {
    const list = reminders ?? [];
    const kw = searchText.trim().toLowerCase();
    if (!kw) return list;
    return list.filter(
      (r) =>
        (r.wechat_name ?? '').toLowerCase().includes(kw) ||
        r.user_number.toLowerCase().includes(kw)
    );
  }, [reminders, searchText]);

  // 最近一次同步时间（取列表中最新一条 last_synced_at）
  const lastSyncedAt = useMemo(() => {
    const list = allStudents ?? [];
    const times = list
      .map((s) => s.last_synced_at)
      .filter((t): t is string => !!t)
      .sort()
      .reverse();
    return times[0] ?? null;
  }, [allStudents]);

  // 加载态
  if (campLoading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin />
      </div>
    );
  }

  if (!camp) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description="未找到该行动营" />
      </div>
    );
  }

  const syncDescText = `带教 ${camp.total_days} 天学员 · 上次同步 ${
    lastSyncedAt ? dayjs(lastSyncedAt).format('MM/DD HH:mm') : '尚未同步'
  }`;

  return (
    <div style={{ padding: 24 }}>
      {/* ============ 页头 ============ */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
            学员看板{' '}
            <span
              style={{
                background: 'var(--volunteer-bg)',
                color: 'var(--volunteer-fg)',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: 600,
                marginLeft: 6,
                verticalAlign: 'middle',
              }}
            >
              志愿者
            </span>
          </h2>
          <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
            {camp.name} · {syncDescText}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Tooltip title="每日 09:00 自动调用破局读接口拉取最新打卡数据">
            <Tag
              icon={<span style={{ marginRight: 2 }}>⏱</span>}
              style={{
                background: '#f3f4f6',
                color: 'var(--text-sub)',
                border: 'none',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                fontWeight: 600,
                margin: 0,
              }}
            >
              定时同步：每日 09:00
            </Tag>
          </Tooltip>
          {/* 初始化学员档案 / 刷新学员档案：列表为空显示主按钮，否则用次按钮。
             仅在用户填过 actionId 时启用；否则引导用户先到 CreateCamp 填写。 */}
          {camp.poju_action_id ? (
            (allStudents?.length ?? 0) === 0 ? (
              <Button
                type="primary"
                icon={<TeamOutlined />}
                loading={initMut.isPending}
                onClick={() => handleArchiveAction('init')}
              >
                初始化学员档案
              </Button>
            ) : (
              <Button
                icon={<ReloadOutlined />}
                loading={refreshMut.isPending}
                onClick={() => handleArchiveAction('refresh')}
              >
                刷新学员档案
              </Button>
            )
          ) : (
            <Tooltip title="请到创建营页面填写破局 actionId 后再初始化">
              <Button icon={<TeamOutlined />} disabled>
                初始化学员档案
              </Button>
            </Tooltip>
          )}
          <Button
            type="primary"
            icon={<SyncOutlined />}
            loading={syncMut.isPending}
            onClick={handleSync}
          >
            立即同步
          </Button>
          <DeleteCampButton campId={camp.id} campName={camp.name} />
        </div>
      </div>

      {/* ============ 统计 4 卡 ============ */}
      <Row gutter={[14, 14]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={12} md={6}>
          <StatCard primary={counts.all} label="带教学员" hint={`营 ${camp.name}`} />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={<span style={{ color: 'var(--warning)' }}>{counts.pending}</span>}
            label="待评改"
            hint="已提交等待志愿者评改"
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={todayCheckedInCount}
            label="今日已打卡"
            hint="含待评改 + 已评改"
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <StatCard
            primary={
              <span style={{ color: counts.insufficient > 0 ? 'var(--danger)' : undefined }}>
                {counts.insufficient}
              </span>
            }
            label="打卡不足需提醒"
            hint={counts.insufficient > 0 ? '请主动联系' : '当前无落后学员'}
          />
        </Col>
      </Row>

      {/* ============ 学员表格卡 ============ */}
      <Card style={{ borderRadius: 10 }} bodyStyle={{ padding: 16 }}>
        {/* Tab + 搜索 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Tabs
            activeKey={tab}
            onChange={(k) => setTab(k as TabKey)}
            items={[
              { key: 'all', label: `全部 ${counts.all}` },
              { key: 'pending', label: `待评改 ${counts.pending}` },
              { key: 'insufficient', label: `打卡不足 ${counts.insufficient}` },
              { key: 'graded', label: `已评改 ${counts.graded}` },
              { key: 'remind', label: `待提醒 ${counts.remind}` },
            ]}
            style={{ marginBottom: -16 }}
          />
          <Input
            allowClear
            prefix={<SearchOutlined style={{ color: 'var(--text-light)' }} />}
            placeholder="搜索学员昵称 / 微信"
            style={{ width: 240 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </div>

        {/* 表格：待提醒 tab / 全部 tab 用破局 reminders 数据；其他 tab 走学员看板 */}
        {tab === 'remind' || tab === 'all' ? (
          <ReminderTable
            loading={remindersLoading}
            data={filteredReminders}
            campId={campId}
            totalDays={camp?.total_days ?? 0}
          />
        ) : tab === 'pending' ? (
          <PendingGradeTable
            loading={!pendingGrades && !!campId}
            data={filteredPendingGrades}
            campId={campId}
          />
        ) : (
          <StudentTable
            loading={studentsLoading}
            data={filteredStudents}
            campId={campId}
            minDays={camp.min_checkin_days}
          />
        )}
        <div style={{ fontSize: 12, color: 'var(--text-light)', marginTop: 12 }}>
          {tab === 'all' ? (
            <>显示 {filteredReminders.length} / {reminders?.length ?? 0} 名学员（破局实时数据）</>
          ) : tab === 'remind' ? (
            <>显示 {filteredReminders.length} / {reminders?.length ?? 0} 条待提醒</>
          ) : tab === 'pending' ? (
            <>显示 {filteredPendingGrades.length} / {pendingGrades?.length ?? 0} 条待评改打卡</>
          ) : (
            <>显示 {filteredStudents.length} / {students?.length ?? 0} 名学员</>
          )}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

type TabKey = 'all' | 'pending' | 'insufficient' | 'graded' | 'remind';

interface StatCardProps {
  primary: React.ReactNode;
  label: string;
  hint?: string;
}

/** 统计卡（design.md 4.5 stat：大数字 + 标签）。 */
function StatCard({ primary, label, hint }: StatCardProps) {
  return (
    <Card style={{ borderRadius: 10, height: '100%' }} bodyStyle={{ padding: 16 }}>
      <div style={{ fontSize: 26, fontWeight: 700, lineHeight: 1.2 }}>{primary}</div>
      <div style={{ fontSize: 12, color: 'var(--text-sub)', marginTop: 4 }}>{label}</div>
      {hint && (
        <div style={{ fontSize: 11, color: 'var(--text-light)', marginTop: 6 }}>{hint}</div>
      )}
    </Card>
  );
}

interface StudentTableProps {
  loading: boolean;
  data: StudentSummary[];
  campId: number | undefined;
  minDays: number;
}

/** 待评改打卡列表：每行 = 一条待评 CheckinRecord；点击行进入评改页。 */
function PendingGradeTable({
  loading,
  data,
  campId,
}: {
  loading: boolean;
  data: PendingGradeOut[];
  campId: number | undefined;
}) {
  const columns: ColumnsType<PendingGradeOut> = [
    {
      title: '学员',
      dataIndex: 'student_nickname',
      key: 'student_nickname',
      width: 140,
      render: (nick: string) => <span style={{ fontWeight: 600 }}>{nick}</span>,
    },
    {
      title: 'Day',
      dataIndex: 'day_number',
      key: 'day_number',
      width: 70,
      render: (d: number) => `Day${d}`,
    },
    {
      title: '提交日期',
      dataIndex: 'checkin_date',
      key: 'checkin_date',
      width: 120,
    },
    {
      title: '提交时间',
      dataIndex: 'submitted_at',
      key: 'submitted_at',
      width: 150,
      render: (t: string | null | undefined) =>
        t ? dayjs(t).format('MM/DD HH:mm') : <span style={{ color: 'var(--text-light)' }}>—</span>,
    },
    {
      title: '打卡摘要',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      render: (c: string | null | undefined) =>
        c ? c : <span style={{ color: 'var(--text-light)' }}>（无内容）</span>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, row) => (
        <Link
          to={`/camp/${campId}/volunteer/grade?camp=${campId}&student=${row.student_id}&checkin=${row.checkin_id}`}
        >
          <Button type="primary" size="small" icon={<EditOutlined />}>
            去评改
          </Button>
        </Link>
      ),
    },
  ];

  if (!loading && data.length === 0) {
    return <Empty description="暂无待评改打卡" style={{ padding: '32px 0' }} />;
  }
  return (
    <Table<PendingGradeOut>
      rowKey="checkin_id"
      loading={loading}
      dataSource={data}
      columns={columns}
      pagination={false}
      size="middle"
    />
  );
}

/** 学员表格：根据 status 派生徽章颜色与距目标文案。 */
function StudentTable({ loading, data, campId, minDays }: StudentTableProps) {
  const columns: ColumnsType<StudentSummary> = [
    {
      title: '学员',
      dataIndex: 'nickname',
      key: 'nickname',
      width: 140,
      render: (nick: string, row) => (
        <div>
          <div style={{ fontWeight: 600 }}>{nick}</div>
          {row.wechat && (
            <div style={{ fontSize: 11, color: 'var(--text-light)' }}>{row.wechat}</div>
          )}
        </div>
      ),
    },
    {
      title: '已打卡',
      dataIndex: 'current_day',
      key: 'current_day',
      width: 90,
      render: (day: number | null | undefined) =>
        day == null ? <span style={{ color: 'var(--text-light)' }}>—</span> : `Day${day}`,
    },
    {
      title: '有效天数',
      key: 'valid_days',
      width: 110,
      render: (_: unknown, row) => (
        <span>
          {row.valid_days} <span style={{ color: 'var(--text-light)' }}>/ {minDays}</span>
        </span>
      ),
    },
    {
      title: '距目标',
      key: 'gap',
      width: 130,
      render: (_: unknown, row) => {
        const gap = row.gap_to_min;
        if (gap <= 0) {
          return (
            <span style={{ color: 'var(--success)' }}>
              已达标（超 {-gap}）
            </span>
          );
        }
        const isInsufficient = row.status === 'unqualified';
        return (
          <span
            style={{
              color: isInsufficient ? 'var(--danger)' : 'var(--text)',
            }}
          >
            差 {gap}
            {isInsufficient && <span style={{ marginLeft: 6 }}>⚠</span>}
          </span>
        );
      },
    },
    {
      title: '最近星级',
      dataIndex: 'last_stars',
      key: 'last_stars',
      width: 110,
      render: (stars: number | null | undefined) =>
        stars == null ? (
          <span style={{ color: 'var(--text-light)' }}>—</span>
        ) : (
          <Stars stars={stars} />
        ),
    },
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_: unknown, row) => <StatusBadge status={row.status} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: unknown, row) => (
        <div style={{ display: 'flex', gap: 6 }}>
          {row.status === 'ongoing' ? (
            <Link to={`/camp/${campId}/volunteer/grade?camp=${campId}&student=${row.id}`}>
              <Button type="primary" size="small" icon={<EditOutlined />}>
                去评改
              </Button>
            </Link>
          ) : (
            <Link to={`/camp/${campId}/volunteer/archive/${row.id}`}>
              <Button size="small" icon={<FileTextOutlined />}>
                查看档案
              </Button>
            </Link>
          )}
          {/* 已达标 / 未达标也可点击档案查看完整历史 */}
          {row.status === 'ongoing' && (
            <Link to={`/camp/${campId}/volunteer/archive/${row.id}`}>
              <Button size="small">档案</Button>
            </Link>
          )}
        </div>
      ),
    },
  ];

  if (!loading && data.length === 0) {
    return <Empty description="该筛选下暂无学员" style={{ padding: '32px 0' }} />;
  }

  return (
    <Table<StudentSummary>
      rowKey="id"
      loading={loading}
      dataSource={data}
      columns={columns}
      pagination={false}
      size="middle"
    />
  );
}

/** 星级渲染（金色实心 + 灰色空心）。 */
function Stars({ stars }: { stars: number }) {
  return (
    <span style={{ color: 'var(--star)', letterSpacing: 1 }}>
      {'★'.repeat(Math.max(0, Math.min(3, stars)))}
      <span style={{ color: 'var(--text-light)' }}>
        {'☆'.repeat(Math.max(0, 3 - stars))}
      </span>
    </span>
  );
}

/** 状态徽章（映射 StudentStatus → 颜色与文案）。 */
function StatusBadge({ status }: { status: StudentStatus }) {
  if (status === 'ongoing') return <Tag color="orange">待评改</Tag>;
  if (status === 'unqualified') return <Tag color="red">打卡不足</Tag>;
  if (status === 'qualified') return <Tag color="green">已评改</Tag>;
  return <Tag>{status}</Tag>;
}

/**
 * 待提醒 / 全部 学员表格。
 *
 * 数据源：useReminders → GET /api/volunteer/camps/{id}/reminders（实时拉取破局）。
 * 列严格按需求文档：
 *   学员 | 打卡天数/总天数 | 可休息天数 | 状态 | 操作
 *
 * - 学员显示 wechat_name，回退 user_number
 * - 打卡天数/总天数：clockInDays / camp.total_days
 * - 状态：is_done=true → "已提醒"；否则按 remind_status 字符串展示
 * - 操作：本地 student_id 命中 → 「查看档案」；否则「未关联」
 */
function ReminderTable({
  loading,
  data,
  campId,
  totalDays,
}: {
  loading: boolean;
  data: ReminderItem[];
  campId: number | undefined;
  totalDays: number;
}) {
  const columns: ColumnsType<ReminderItem> = [
    {
      title: '学员',
      key: 'wechat_name',
      width: 160,
      render: (_: unknown, row) => (
        <div>
          <div style={{ fontWeight: 600 }}>{row.wechat_name || row.user_number}</div>
          <div style={{ fontSize: 11, color: 'var(--text-light)' }}>{row.user_number}</div>
        </div>
      ),
    },
    {
      title: '打卡天数/总天数',
      key: 'clock_in_days',
      width: 160,
      render: (_: unknown, row) => (
        <span>
          {row.clock_in_days} <span style={{ color: 'var(--text-light)' }}>/ {totalDays}</span>
        </span>
      ),
    },
    {
      title: '可休息天数',
      dataIndex: 'rest_days',
      key: 'rest_days',
      width: 110,
      render: (n: number) => <span>{n ?? 0}</span>,
    },
    {
      title: '状态',
      key: 'remind_status',
      width: 130,
      render: (_: unknown, row) =>
        row.is_done ? (
          <Tag color="green">已提醒</Tag>
        ) : (
          <Tag color="orange">{row.remind_status || '待提醒'}</Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: unknown, row) =>
        row.student_id ? (
          <Link to={`/camp/${campId}/volunteer/archive/${row.student_id}`}>
            <Button size="small" icon={<FileTextOutlined />}>
              查看档案
            </Button>
          </Link>
        ) : (
          <Tooltip title="本地未关联该学员，请先初始化档案">
            <span style={{ color: 'var(--text-light)' }}>未关联</span>
          </Tooltip>
        ),
    },
  ];

  if (!loading && data.length === 0) {
    return <Empty description="当前没有学员数据" style={{ padding: '32px 0' }} />;
  }
  return (
    <Table<ReminderItem>
      rowKey="user_number"
      loading={loading}
      dataSource={data}
      columns={columns}
      pagination={false}
      size="middle"
    />
  );
}