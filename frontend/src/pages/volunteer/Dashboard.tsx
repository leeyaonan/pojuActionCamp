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
  Select,
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
} from '@/api/types';

// ---------------------------------------------------------------------------
// 业务状态（2026-07-11 重做）：不再透传破局 remind_status，由前端按
// (打卡天数, 可休息天数, 目标天数) 派生。优先级：已上岸 > 已失败 > 未打卡 > 危险 > 进度正常。
// ---------------------------------------------------------------------------

type ReminderStatus =
  | 'not_started'   // 未打卡
  | 'failed'        // 已失败
  | 'completed'     // 已上岸
  | 'danger'        // 危险
  | 'on_track';     // 进度正常

interface ReminderStatusMeta {
  label: string;  // 中文显示
  color: string;  // antd Tag color
}

const REMINDER_STATUS_META: Record<ReminderStatus, ReminderStatusMeta> = {
  not_started: { label: '未打卡',   color: 'default' },
  failed:      { label: '已失败',   color: 'red'    },
  completed:   { label: '已上岸',   color: 'green'  },
  danger:      { label: '危险',     color: 'orange' },
  on_track:    { label: '进度正常', color: 'blue'   },
};

/**
 * 判定学员业务状态。
 *
 * - 已上岸：打卡天数已达最低目标（camp.min_checkin_days）
 * - 已失败：可休息天数 < 0（无论打卡多少都已透支，沉底）
 * - 未打卡：打卡 = 0 且可休息仍 ≥ 0（营刚开始阶段的零打卡学员）
 *   → 注意：若一直未打卡，营进入中后期 rest_days<0 后会自动归到"已失败"
 * - 危险：可休息天数 1~2 天
 * - 进度正常：其余（有打卡、rest ≥ 3、未达最低目标）
 */
function classifyReminderStatus(
  clockInDays: number,
  restDays: number,
  target: number,
): ReminderStatus {
  if (clockInDays >= target) return 'completed';
  if (restDays < 0) return 'failed';
  if (clockInDays === 0) return 'not_started';
  if (restDays < 3) return 'danger';
  return 'on_track';
}

/**
 * P6 志愿者·学员看板（design.md 6.P6 + ui-prototype #volunteer-dashboard）。
 *
 * 页面结构（2026-07-11 精简）：
 * 1. 页头：标题「学员看板」+ 志愿者徽章 + 营名 + 上次同步时间 +
 *    「⏱ 定时同步」标签 + 「🔄 立即同步」主按钮。
 * 2. 统计 3 卡：带教学员 / 待评改（warn）/ 今日已打卡。
 * 3. Tab 行：仅 3 个 tab：全部 / 待评改 / 待提醒（带数量徽章）+ 搜索框。
 * 4. 学员表格（全部/待提醒）：学员 / 打卡天数/总天数 / 可休息天数 / 状态 / 操作。
 * 5. 学员表格（待评改）：学员 / Day / 提交日期 / 提交时间 / 打卡摘要 / 操作。
 *
 * 数据源：
 * - useCamp(campId)         营基本信息（名称 / 起止 / 总天数）
 * - useReminders(campId)    破局 member-clock-in-status 实时拉取（全部 / 待提醒 tab）
 * - usePendingGrades(campId) 待评改列表（待评改 tab）
 * - useSyncBoard(campId)    手动同步 mutation
 */
export default function VolunteerDashboard() {
  const params = useParams<{ id: string }>();
  const campId = params.id ? Number(params.id) : undefined;

  // 营详情（用于副标题与营名）
  const { data: camp, isLoading: campLoading } = useCamp(campId);
  // 待评改列表（每条 = 一条 CheckinRecord；营未开始时应为空）
  const { data: pendingGrades } = usePendingGrades(campId);

  // 当前 Tab（精简 2 个）：'all' | 'pending'
  //  - 'all'     → 全部学员（数据来自破局 member-clock-in-status 实时拉取，按你给的新表头）
  //  - 'pending' → 真·待评改打卡列表（/grades/pending）
  const [tab, setTab] = useState<TabKey>('all');
  // 学员昵称搜索（前端过滤）
  const [searchText, setSearchText] = useState('');
  // 全部 tab 的业务状态筛选（默认 'all'）
  const [statusFilter, setStatusFilter] = useState<ReminderStatus | 'all'>('all');

  // 手动同步
  const syncMut = useSyncBoard(campId ?? -1);
  const { message, modal } = AntApp.useApp();

  // 初始化 / 刷新学员档案（拉破局 query-people）
  const initMut = useInitArchive(campId ?? -1);
  const refreshMut = useRefreshArchive(campId ?? -1);

  // 「全部」tab 的破局实时数据（reminders 接口；本页面也用作「全部」视图的数据源）
  const { data: reminders, isLoading: remindersLoading } = useReminders(campId);

  // 两个 Tab 的数量：
  //  - all      → 破局 reminders 总数
  //  - pending  → 真·待评改数
  const counts = useMemo(() => ({
    all: (reminders ?? []).length,
    pending: (pendingGrades ?? []).length,
  }), [pendingGrades, reminders]);

  // 今日已打卡近似 = 待评改列表数；MVP 简化（接口已存在 /grading_audit/today
  // 时可接入）。营未开始时 pendingGrades 为空 → 自然落到 0。
  const todayCheckedInCount = useMemo(
    () => (pendingGrades ?? []).length,
    [pendingGrades]
  );

  // 同步处理（无 useStudents 后无需手动 refetch；syncMut 内部已 invalidate）
  const handleSync = async () => {
    if (!campId) return;
    try {
      const res = await syncMut.mutateAsync();
      if (res.success) {
        message.success(res.message || '同步成功');
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
   * 仅在尚未初始化（reminders 为空）时弹，避免无意义打扰。
   */
  useEffect(() => {
    if (!campId) return;
    let pendingId: string | null = null;
    try {
      pendingId = sessionStorage.getItem('pending_init_camp_id');
    } catch {
      // 忽略
    }
    if (pendingId && pendingId === String(campId) && !remindersLoading) {
      try {
        sessionStorage.removeItem('pending_init_camp_id');
      } catch {
        // 忽略
      }
      const listEmpty = (reminders?.length ?? 0) === 0;
      if (listEmpty) {
        // 用 setTimeout 推到下一个 tick，避免 Modal 与首次渲染抢焦点
        setTimeout(() => handleArchiveAction('init'), 100);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campId, remindersLoading, reminders?.length]);

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

  // 最近一次同步时间（取 camp.updated_at 作为最近一次主动同步的近似）
  const lastSyncedAt = useMemo(() => camp?.updated_at ?? null, [camp?.updated_at]);

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
            (reminders?.length ?? 0) === 0 ? (
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

      {/* ============ 统计 3 卡 ============ */}
      <Row gutter={[14, 14]} style={{ marginBottom: 20 }}>
        <Col xs={24} sm={12} md={8}>
          <StatCard primary={counts.all} label="带教学员" hint={`营 ${camp.name}`} />
        </Col>
        <Col xs={24} sm={12} md={8}>
          <StatCard
            primary={<span style={{ color: 'var(--warning)' }}>{counts.pending}</span>}
            label="待评改"
            hint="已提交等待志愿者评改"
          />
        </Col>
        <Col xs={24} sm={12} md={8}>
          <StatCard
            primary={todayCheckedInCount}
            label="今日已打卡"
            hint="含待评改 + 已评改"
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
            ]}
            style={{ marginBottom: -16 }}
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {/* 状态筛选仅「全部」tab 生效；切到「待评改」时自动隐藏 */}
            {tab === 'all' && (
              <Select<ReminderStatus | 'all'>
                value={statusFilter}
                onChange={setStatusFilter}
                style={{ width: 140 }}
                options={[
                  { value: 'all',         label: '全部状态' },
                  { value: 'not_started', label: '未打卡' },
                  { value: 'failed',      label: '已失败' },
                  { value: 'completed',   label: '已上岸' },
                  { value: 'danger',      label: '危险' },
                  { value: 'on_track',    label: '进度正常' },
                ]}
              />
            )}
            <Input
              allowClear
              prefix={<SearchOutlined style={{ color: 'var(--text-light)' }} />}
              placeholder="搜索学员昵称 / 微信"
              style={{ width: 240 }}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
          </div>
        </div>

        {/* 表格：待提醒 tab / 全部 tab 用破局 reminders 数据；其他 tab 走学员看板 */}
        {tab === 'all' ? (
          <ReminderTable
            loading={remindersLoading}
            data={filteredReminders}
            campId={campId}
            totalDays={camp?.total_days ?? 0}
            minCheckinDays={camp?.min_checkin_days ?? 1}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
          />
        ) : (
          <PendingGradeTable
            loading={!pendingGrades && !!campId}
            data={filteredPendingGrades}
            campId={campId}
          />
        )}
        {tab === 'pending' && (
          <div style={{ fontSize: 12, color: 'var(--text-light)', marginTop: 12 }}>
            显示 {filteredPendingGrades.length} / {pendingGrades?.length ?? 0} 条待评改打卡
          </div>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

type TabKey = 'all' | 'pending';

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


/**
 * 「全部」tab 学员表格。
 *
 * 数据源：useReminders → GET /api/volunteer/camps/{id}/reminders（实时拉取破局）。
 *
 * 列严格按需求文档：
 *   学员 | 打卡天数/总天数 | 可休息天数 | 状态 | 操作
 *
 * 状态（2026-07-11 重做）：不再透传破局 remind_status，按
 * (clockInDays, restDays, minCheckinDays) 派生业务状态：
 *   已上岸 / 已失败 / 未打卡 / 危险 / 进度正常。
 *
 * 排序：clockInDays 升序、restDays 升序（越少越靠前）。
 * 筛选：statusFilter='all' 不过滤，否则按业务状态精确匹配。
 *
 * 操作：本地 student_id 命中 → 「查看档案」；否则「未关联」。
 */
function ReminderTable({
  loading,
  data,
  campId,
  totalDays,
  minCheckinDays,
  statusFilter,
  onStatusFilterChange,
}: {
  loading: boolean;
  data: ReminderItem[];
  campId: number | undefined;
  totalDays: number;
  minCheckinDays: number;
  statusFilter: ReminderStatus | 'all';
  onStatusFilterChange: (v: ReminderStatus | 'all') => void;
}) {
  // 先排序：打卡天数升序 → 可休息天数升序（少的越危险，越靠前）
  const sorted = useMemo(
    () =>
      [...data].sort((a, b) => {
        if (a.clock_in_days !== b.clock_in_days) {
          return a.clock_in_days - b.clock_in_days;
        }
        return a.rest_days - b.rest_days;
      }),
    [data],
  );

  // 再按业务状态过滤（先排后筛，过滤后顺序保留）
  const filtered = useMemo(
    () =>
      statusFilter === 'all'
        ? sorted
        : sorted.filter(
            (r) =>
              classifyReminderStatus(r.clock_in_days, r.rest_days, minCheckinDays) ===
              statusFilter,
          ),
    [sorted, statusFilter, minCheckinDays],
  );

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
      key: 'status',
      width: 120,
      render: (_: unknown, row) => {
        const status = classifyReminderStatus(
          row.clock_in_days,
          row.rest_days,
          minCheckinDays,
        );
        const meta = REMINDER_STATUS_META[status];
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
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

  if (!loading && filtered.length === 0) {
    return (
      <Empty
        description={statusFilter === 'all' ? '当前没有学员数据' : '当前筛选条件下没有学员'}
        style={{ padding: '32px 0' }}
      />
    );
  }
  return (
    <>
      <Table<ReminderItem>
        rowKey="user_number"
        loading={loading}
        dataSource={filtered}
        columns={columns}
        pagination={false}
        size="middle"
      />
      <div style={{ fontSize: 12, color: 'var(--text-light)', marginTop: 12 }}>
        显示 {filtered.length} / {data.length} 名学员（破局实时数据）
      </div>
    </>
  );
}