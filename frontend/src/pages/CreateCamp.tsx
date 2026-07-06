import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  App as AntApp,
} from 'antd';
import {
  ArrowLeftOutlined,
  BookOutlined,
  UserOutlined,
  TeamOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { useCreateCamp } from '@/hooks/useCamps';
import type { Role } from '@/api/types';

/**
 * P2 创建行动营（design.md §6 P2 + §5 流程 C）。
 *
 * 页面结构：
 * - 页头：标题 + 副标题 + 返回。
 * - Form：
 *   1. 身份（卡片单选：学员/志愿者，不可改）
 *   2. 行动营名称
 *   3. 简介（可选）
 *   4. 总天数 + 最低打卡完成天数（实时联动：min = round(total * 0.6)）
 *   5. 开始 / 结束日期（start<end 校验）
 * - 提示条：创建后下一步
 * - 按钮：创建 / 取消
 *
 * 提交流程：useCreateCamp mutation；成功后按身份跳转到对应工作台。
 */

type FormValues = {
  role: Role;
  name: string;
  description?: string;
  total_days: number;
  min_checkin_days: number;
  range: [Dayjs, Dayjs];
  poju_action_id?: string;
};

const DEFAULT_TOTAL_DAYS = 30;
const MIN_DAYS_RATIO = 0.6;

export default function CreateCamp() {
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const [form] = Form.useForm<FormValues>();

  // 监听总天数变化 → 实时联动最低打卡天数（×0.6 四舍五入），并以"用户是否手动改过"为标志避免覆盖。
  const [minDaysTouched, setMinDaysTouched] = useState(false);
  const totalDays = Form.useWatch('total_days', form);
  const minDays = Form.useWatch('min_checkin_days', form);

  useEffect(() => {
    if (minDaysTouched) return;
    const total = Number(totalDays);
    if (!Number.isFinite(total) || total <= 0) return;
    const suggested = Math.round(total * MIN_DAYS_RATIO);
    if (suggested !== Number(minDays)) {
      form.setFieldsValue({ min_checkin_days: suggested });
    }
  }, [totalDays, minDaysTouched, minDays, form]);

  const mutation = useCreateCamp();

  const initialValues = useMemo<FormValues>(
    () => ({
      role: 'student',
      name: '',
      description: '',
      total_days: DEFAULT_TOTAL_DAYS,
      min_checkin_days: Math.round(DEFAULT_TOTAL_DAYS * MIN_DAYS_RATIO),
      range: [dayjs(), dayjs().add(DEFAULT_TOTAL_DAYS - 1, 'day')],
      poju_action_id: '',
    }),
    []
  );

  const handleFinish = async (values: FormValues) => {
    const [start, end] = values.range;
    const actionId = values.poju_action_id?.trim();
    const payload = {
      name: values.name.trim(),
      role: values.role,
      description: values.description?.trim() || undefined,
      total_days: values.total_days,
      start_date: start.format('YYYY-MM-DD'),
      end_date: end.format('YYYY-MM-DD'),
      min_checkin_days: values.min_checkin_days,
      poju_action_id: actionId ? actionId : undefined,
    };
    try {
      const camp = await mutation.mutateAsync(payload);
      message.success(`已创建行动营：${camp.name}`);
      // 志愿者身份 + 已填 actionId → 通知 Dashboard 自动弹窗"是否立即初始化档案"。
      // 用 sessionStorage 而非 query，避免 URL 暴露内部状态；Dashboard 进入时
      // 自动清理。
      if (camp.role === 'volunteer' && actionId && camp.id) {
        try {
          sessionStorage.setItem('pending_init_camp_id', String(camp.id));
        } catch {
          // 忽略 sessionStorage 不可用（隐私模式）
        }
      }
      const target =
        camp.role === 'student'
          ? `/camp/${camp.id}/student`
          : `/camp/${camp.id}/volunteer`;
      navigate(target);
    } catch {
      // useCreateCamp 内部已 toast；此处仅中断
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 880 }}>
      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 20,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>新建行动营</h2>
          <div style={{ color: 'var(--text-sub)', fontSize: 13, marginTop: 4 }}>
            创建后将根据所选身份进入对应工作台
          </div>
        </div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          返回
        </Button>
      </div>

      <Card
        bordered={false}
        style={{ borderRadius: 10, boxShadow: 'var(--shadow-card)' }}
        bodyStyle={{ padding: 24 }}
      >
        <Form<FormValues>
          form={form}
          layout="vertical"
          initialValues={initialValues}
          requiredMark={(label, info) => (
            <span>
              {label}
              {info.required && <span style={{ color: 'var(--danger)', marginLeft: 4 }}>*</span>}
            </span>
          )}
          onFinish={handleFinish}
          onValuesChange={(changed) => {
            if ('min_checkin_days' in changed) {
              setMinDaysTouched(true);
            }
            // 若用户把 total_days 改为 0/空，重置 touched 让初始联动恢复
            if ('total_days' in changed && !changed.total_days) {
              setMinDaysTouched(false);
            }
          }}
        >
          {/* 1. 身份（卡片单选） */}
          <Form.Item
            label="身份"
            name="role"
            rules={[{ required: true, message: '请选择身份' }]}
            extra={
              <span style={{ color: 'var(--text-sub)', fontSize: 12 }}>
                单期行动营仅一个主身份，创建后不可更改
              </span>
            }
          >
            <RolePicker />
          </Form.Item>

          {/* 2. 行动营名称 */}
          <Form.Item
            label="行动营名称"
            name="name"
            rules={[
              { required: true, message: '请输入行动营名称' },
              { max: 60, message: '名称最多 60 字' },
            ]}
          >
            <Input placeholder="例如：AI写作破局营" allowClear maxLength={60} />
          </Form.Item>

          {/* 3. 简介 */}
          <Form.Item
            label="简介"
            name="description"
            rules={[{ max: 500, message: '简介最多 500 字' }]}
          >
            <Input.TextArea
              placeholder="本期主题、训练目标……"
              autoSize={{ minRows: 3, maxRows: 6 }}
              maxLength={500}
              showCount
            />
          </Form.Item>

          {/* 4. 总天数 + 最低打卡天数 */}
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item
              label="总天数"
              name="total_days"
              style={{ flex: 1 }}
              rules={[
                { required: true, message: '请输入总天数' },
                { type: 'number', min: 1, max: 365, message: '范围 1~365' },
              ]}
            >
              <InputNumber
                min={1}
                max={365}
                step={1}
                style={{ width: '100%' }}
                placeholder="30"
              />
            </Form.Item>

            <Form.Item
              label="最低打卡完成天数"
              name="min_checkin_days"
              style={{ flex: 1 }}
              extra={
                <span style={{ color: 'var(--text-sub)', fontSize: 12 }}>
                  默认 = 总天数 × 0.6（四舍五入），可手动修改。达到后可退押金
                </span>
              }
              rules={[
                { required: true, message: '请输入最低打卡天数' },
                { type: 'number', min: 1, max: 365, message: '范围 1~365' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    const total = Number(getFieldValue('total_days'));
                    if (!value || !total) return Promise.resolve();
                    if (value > total) {
                      return Promise.reject(new Error('最低天数不能超过总天数'));
                    }
                    return Promise.resolve();
                  },
                }),
              ]}
            >
              <InputNumber
                min={1}
                max={365}
                step={1}
                style={{ width: '100%' }}
                placeholder="18"
              />
            </Form.Item>
          </div>

          {/* 5. 开始 / 结束日期 */}
          <Form.Item
            label="开始 / 结束日期"
            name="range"
            rules={[
              { required: true, message: '请选择起止日期' },
              {
                validator(_, value) {
                  if (!value || value.length !== 2) {
                    return Promise.reject(new Error('请选择起止日期'));
                  }
                  const [start, end] = value;
                  if (!start.isValid() || !end.isValid()) {
                    return Promise.reject(new Error('日期不合法'));
                  }
                  if (!end.isAfter(start)) {
                    return Promise.reject(new Error('结束日期必须晚于开始日期'));
                  }
                  return Promise.resolve();
                },
              },
            ]}
            extra={
              <span style={{ color: 'var(--text-sub)', fontSize: 12 }}>
                应与开始时间 + 总天数相符
              </span>
            }
          >
            <DatePicker.RangePicker
              style={{ width: '100%' }}
              format="YYYY-MM-DD"
              allowClear={false}
            />
          </Form.Item>

          {/* 6. 破局行动营 ID（actionId），所有身份均可填；非必填 */}
          <Form.Item
            label="破局行动营 ID（actionId）"
            name="poju_action_id"
            extra={
              <span style={{ color: 'var(--text-sub)', fontSize: 12 }}>
                可选。在破局平台行动营详情页 URL 中查看（UUID 格式）。志愿者身份用于后续"初始化学员档案"
              </span>
            }
            rules={[
              { max: 64, message: '最多 64 字符' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value) return Promise.resolve();
                  const trimmed = String(value).trim();
                  if (trimmed && !/^[0-9a-fA-F-]{8,64}$/.test(trimmed)) {
                    return Promise.reject(new Error('actionId 格式不正确（应为 UUID）'));
                  }
                  return Promise.resolve();
                },
              }),
            ]}
          >
            <Input placeholder="例如：a8e2f51d-b83e-4721-9d44-9a9a92c7af1e" allowClear />
          </Form.Item>

          {/* 提示条 */}
          <div
            style={{
              background: 'var(--primary-light)',
              border: '1px solid var(--primary)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 14px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              color: 'var(--text)',
              fontSize: 13,
              marginBottom: 20,
            }}
          >
            <InfoCircleOutlined
              style={{ color: 'var(--primary)', marginTop: 2, flexShrink: 0 }}
            />
            <div>
              创建后下一步：进入「手册管理」上传手册文本 → 学员身份将自动规划学习路线；志愿者身份需到「接口配置」填入 Token。
            </div>
          </div>

          {/* 操作按钮 */}
          <div style={{ display: 'flex', gap: 12 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={mutation.isPending}
              disabled={mutation.isPending}
            >
              创建行动营
            </Button>
            <Button onClick={() => navigate('/')} disabled={mutation.isPending}>
              取消
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  );
}

/**
 * 身份卡片单选（学员 / 志愿者）。
 * 与 Form.Item(name="role") 集成：受控展示 + 主动提交值。
 */
function RolePicker() {
  const value = Form.useWatch('role');
  const form = Form.useFormInstance<FormValues>();
  const options: Array<{
    key: Role;
    icon: React.ReactNode;
    title: string;
    desc: string;
    bg: string;
    fg: string;
  }> = [
    {
      key: 'student',
      icon: <BookOutlined style={{ fontSize: 18 }} />,
      title: '学员',
      desc: '需交押金、每日打卡，满最低天数退押金',
      bg: 'var(--student-bg)',
      fg: 'var(--student-fg)',
    },
    {
      key: 'volunteer',
      icon: <TeamOutlined style={{ fontSize: 18 }} />,
      title: '志愿者',
      desc: '免押金、免费看手册，负责带教学员与作业评改',
      bg: 'var(--volunteer-bg)',
      fg: 'var(--volunteer-fg)',
    },
  ];

  return (
    <div
      role="radiogroup"
      style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          const next: Role = value === 'student' ? 'volunteer' : 'student';
          form.setFieldsValue({ role: next });
          e.preventDefault();
        }
      }}
    >
      {options.map((opt) => {
        const selected = value === opt.key;
        return (
          <div
            key={opt.key}
            role="radio"
            aria-checked={selected}
            tabIndex={0}
            onClick={() => form.setFieldsValue({ role: opt.key })}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                form.setFieldsValue({ role: opt.key });
                e.preventDefault();
              }
            }}
            style={{
              flex: 1,
              minWidth: 240,
              cursor: 'pointer',
              padding: '14px 16px',
              borderRadius: 'var(--radius-card)',
              border: selected
                ? '2px solid var(--primary)'
                : '1px solid var(--border)',
              background: selected ? 'var(--primary-light)' : 'var(--surface)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              transition: 'all 0.15s',
              outline: 'none',
            }}
          >
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 'var(--radius-sm)',
                background: opt.bg,
                color: opt.fg,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {opt.icon}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 14,
                  fontWeight: 600,
                  color: 'var(--text)',
                  marginBottom: 4,
                }}
              >
                <UserOutlined style={{ fontSize: 12, color: 'var(--text-sub)' }} />
                {opt.title}
                {selected && (
                  <span
                    style={{
                      marginLeft: 4,
                      fontSize: 11,
                      color: 'var(--primary)',
                      background: 'var(--surface)',
                      border: '1px solid var(--primary)',
                      borderRadius: 'var(--radius-pill)',
                      padding: '0 8px',
                    }}
                  >
                    已选中
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-sub)', lineHeight: 1.5 }}>
                {opt.desc}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
