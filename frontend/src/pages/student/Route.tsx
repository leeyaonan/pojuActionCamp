import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Spin,
  Tag,
} from 'antd';
import {
  EditOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  UploadOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import {
  useGenerateRoute,
  useRegenerateRoute,
  useRoute,
  useUpdateDayTask,
} from '@/hooks/useStudent';
import { useCamp } from '@/hooks/useCamps';
import type { DayTaskOut } from '@/api/types';

/**
 * P4 学员·学习路线（student-route）
 *
 * 结构：
 * - 页头：标题 + 学员徽章 + 副标题 + 右侧"重新规划 / 上传手册"按钮
 * - 蓝色提示条：手册无固定按天结构，路线由 AI 自主规划，可编辑
 * - 学习路线列表：
 *   · 按 day_number 升序
 *   · 今天（= Camp.current_day）高亮（主色浅底）
 *   · 已完成（is_completed）灰显
 *   · 每行右侧：编辑按钮；今天额外"去打卡"按钮
 * - 编辑 Modal：title / description / tags（字符串数组）
 * - 重新规划：点击 → modal.confirm 二次确认 → 调 API
 * - 未生成路线：空状态 + "生成学习路线"按钮
 */
export default function StudentRoute() {
  const params = useParams<{ id: string }>();
  const campId = Number(params.id);
  const { modal, message } = App.useApp();

  const { data: camp } = useCamp(Number.isFinite(campId) ? campId : undefined);
  const { data: route, isLoading } = useRoute(Number.isFinite(campId) ? campId : undefined);

  const generateRoute = useGenerateRoute(campId);
  const regenerateRoute = useRegenerateRoute(campId);
  const updateDayTask = useUpdateDayTask(campId);

  // 编辑 Modal 状态
  const [editing, setEditing] = useState<DayTaskOut | null>(null);
  const [editForm] = Form.useForm<{
    title: string;
    description?: string;
    tagsText?: string;
  }>();

  // 排序后的任务列表
  const sortedTasks = useMemo(() => {
    if (!route?.tasks) return [];
    return [...route.tasks].sort((a, b) => a.day_number - b.day_number);
  }, [route]);

  // 当前 Day（未开始 / 已结束时为 null）
  const today = camp?.current_day ?? null;

  // 是否有路线
  const hasRoute = !!route && sortedTasks.length > 0;

  // ---------- 编辑 ----------
  const openEdit = (task: DayTaskOut) => {
    setEditing(task);
    editForm.setFieldsValue({
      title: task.title,
      description: task.description ?? '',
      tagsText: (task.tags ?? [])
        .map((t) => {
          if (typeof t === 'string') return t;
          const v = (t as Record<string, unknown>).name ?? (t as Record<string, unknown>).label;
          return typeof v === 'string' ? v : '';
        })
        .filter(Boolean)
        .join('、'),
    });
  };

  const submitEdit = async () => {
    if (!editing) return;
    try {
      const values = await editForm.validateFields();
      const tagsArr = (values.tagsText ?? '')
        .split(/[、,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((name) => ({ name }));
      await updateDayTask.mutateAsync({
        taskId: editing.id,
        payload: {
          title: values.title,
          description: values.description,
          tags: tagsArr,
        },
      });
      message.success('已保存');
      setEditing(null);
    } catch {
      // AntD validateFields reject：表单已显示错误
    }
  };

  // ---------- 重新规划 ----------
  // BUG-STU-010: 点击先弹确认对话框，避免意外覆盖已编辑任务。
  const handleRegenerateClick = () => {
    modal.confirm({
      title: '重新规划学习路线',
      content:
        '将基于手册重新生成每日任务。会覆盖 AI 自动生成的部分。是否继续？',
      okText: '继续生成',
      cancelText: '取消',
      okButtonProps: { loading: regenerateRoute.isPending },
      onOk: async () => {
        try {
          // 默认保留已编辑内容（与原 keepEdits=true 行为一致，避免误覆盖用户编辑）
          await regenerateRoute.mutateAsync(true);
          message.success('已重新生成学习路线');
        } catch {
          // 已由 hook 内部 toast
        }
      },
    });
  };

  // ---------- 生成 ----------
  const submitGenerate = async () => {
    try {
      await generateRoute.mutateAsync();
      message.success('已生成学习路线');
    } catch {
      // 已 toast
    }
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>学习路线</h2>
            <Tag
              style={{
                background: 'var(--student-bg)',
                color: 'var(--student-fg)',
                border: 'none',
                borderRadius: 10,
                padding: '2px 10px',
                fontSize: 11,
                margin: 0,
              }}
            >
              学员
            </Tag>
          </div>
          <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
            AI 根据手册内容自动规划，可手动编辑调整
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRegenerateClick}
            disabled={!hasRoute}
          >
            重新规划
          </Button>
          <Link to={`/camp/${campId}/manual`}>
            <Button icon={<UploadOutlined />}>上传/更新手册</Button>
          </Link>
        </div>
      </div>

      {/* 蓝色提示条 */}
      <div
        style={{
          background: 'var(--primary-light)',
          color: 'var(--primary)',
          border: '1px solid #c7d2fe',
          borderRadius: 'var(--radius-sm)',
          padding: '10px 14px',
          fontSize: 13,
          marginBottom: 16,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 8,
        }}
      >
        <span>💡</span>
        <span>手册本身无固定按天结构，以上路线由 AI 根据总天数与内容量自主规划，你可逐日编辑。</span>
      </div>

      {/* 路线卡片 */}
      <Card
        style={{
          borderRadius: 'var(--radius-card)',
          border: '1px solid var(--border)',
        }}
        bodyStyle={{ padding: 0 }}
      >
        {isLoading ? (
          <div style={{ padding: 48, textAlign: 'center' }}>
            <Spin />
          </div>
        ) : !hasRoute ? (
          <div style={{ padding: 48 }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <div style={{ color: 'var(--text-sub)' }}>
                  <div style={{ marginBottom: 4 }}>尚未生成学习路线</div>
                  <div style={{ fontSize: 12, color: 'var(--text-light)' }}>
                    生成后将根据手册内容与营期总天数自动规划每日任务
                  </div>
                </div>
              }
            >
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={submitGenerate}
                loading={generateRoute.isPending}
              >
                生成学习路线
              </Button>
            </Empty>
          </div>
        ) : (
          <div>
            {sortedTasks.map((task, idx) => (
              <DayTaskRow
                key={task.id}
                task={task}
                isToday={today !== null && task.day_number === today}
                isLast={idx === sortedTasks.length - 1}
                onEdit={() => openEdit(task)}
              />
            ))}
            <div
              style={{
                padding: '14px 16px',
                textAlign: 'center',
                color: 'var(--text-light)',
                fontSize: 12,
                borderTop: '1px solid var(--border)',
                background: '#fafbfc',
                borderRadius: '0 0 var(--radius-card) var(--radius-card)',
              }}
            >
              共 {sortedTasks.length} 天 · 已完成 {sortedTasks.filter((t) => t.is_completed).length} 天
            </div>
          </div>
        )}
      </Card>

      {/* 编辑 Modal */}
      <Modal
        open={!!editing}
        title={editing ? `编辑 Day ${editing.day_number}` : '编辑'}
        onCancel={() => setEditing(null)}
        onOk={submitEdit}
        okText="保存"
        cancelText="取消"
        confirmLoading={updateDayTask.isPending}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item
            label="标题"
            name="title"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="今日任务标题" maxLength={80} showCount />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea
              placeholder="补充说明、要点、参考章节等"
              rows={4}
              maxLength={400}
              showCount
            />
          </Form.Item>
          <Form.Item
            label="标签"
            name="tagsText"
            extra="多个标签用「、」或英文逗号分隔，例如：手册第3章、SCQA、改写"
          >
            <Input placeholder="如：手册第3章、SCQA、改写" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 单行任务
// ---------------------------------------------------------------------------

function DayTaskRow({
  task,
  isToday,
  isLast,
  onEdit,
}: {
  task: DayTaskOut;
  isToday: boolean;
  isLast: boolean;
  onEdit: () => void;
}) {
  const params = useParams<{ id: string }>();
  const campId = Number(params.id);

  const completed = task.is_completed;

  // 标签展示（兼容字符串或对象结构）
  const tags = (task.tags ?? [])
    .map((t) => {
      if (typeof t === 'string') return t;
      const v = (t as Record<string, unknown>).name ?? (t as Record<string, unknown>).label;
      return typeof v === 'string' ? v : '';
    })
    .filter(Boolean) as string[];

  const dayLabel = isToday ? `Day${task.day_number}·今天` : `Day${task.day_number}`;
  const dayBadgeColor = isToday ? 'blue' : 'default';

  const containerStyle: React.CSSProperties = {
    padding: '12px 16px',
    background: isToday ? 'var(--primary-light)' : 'transparent',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderBottom: isLast ? 'none' : '1px solid var(--border)',
    opacity: completed ? 0.55 : 1,
    transition: 'background .15s',
  };

  return (
    <div style={containerStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
        <Tag
          color={dayBadgeColor}
          style={{
            borderRadius: 6,
            margin: 0,
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          {dayLabel}
        </Tag>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: 'var(--text)',
              textDecoration: completed ? 'line-through' : 'none',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={task.title}
          >
            {task.title}
          </div>
          {task.description && (
            <div
              style={{
                fontSize: 12.5,
                color: 'var(--text-sub)',
                marginTop: 2,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={task.description}
            >
              {task.description}
            </div>
          )}
          {(tags.length > 0 || task.edited) && (
            <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {tags.map((t, i) => (
                <Tag
                  key={`${t}-${i}`}
                  style={{
                    background: '#f3f4f6',
                    color: 'var(--text-sub)',
                    border: 'none',
                    borderRadius: 5,
                    fontSize: 11,
                    margin: 0,
                    padding: '0 6px',
                    lineHeight: '20px',
                  }}
                >
                  {t}
                </Tag>
              ))}
              {task.edited && (
                <Tag
                  style={{
                    background: '#fef3c7',
                    color: '#92400e',
                    border: 'none',
                    borderRadius: 5,
                    fontSize: 11,
                    margin: 0,
                    padding: '0 6px',
                    lineHeight: '20px',
                  }}
                >
                  已编辑
                </Tag>
              )}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        {completed && (
          <Tag color="green" style={{ margin: 0, borderRadius: 6 }}>
            已完成
          </Tag>
        )}
        {isToday && !completed && (
          <Link to={`/camp/${campId}/student/checkin`}>
            <Button type="primary" size="small" icon={<CalendarOutlined />}>
              去打卡
            </Button>
          </Link>
        )}
        <Button size="small" icon={<EditOutlined />} onClick={onEdit}>
          编辑
        </Button>
      </div>
    </div>
  );
}