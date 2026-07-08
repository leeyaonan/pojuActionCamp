/**
 * P11 接口配置。
 *
 * 结构（对齐 design.md P11）：
 * - 页头：标题"接口配置"
 * - Token 配置卡：
 *   - Authorization Token Input.Password（占位 "Bearer eyJhbGc..." 示例）+ 提示
 *   - 接口地址 Input
 *   - Token 状态展示（valid/invalid/unknown badge + 上次校验时间）
 *   - "保存配置"按钮（任一字段变化即可点击）
 * - 接口能力清单卡：表格（接口名/读写类型/接口路径/用途）+ 编辑 Modal
 *
 * 变更记录：
 * - 测试连接入口已屏蔽：后端 /poju/test 已禁用，前端不展示入口；
 *   待真实接口对接后再启用。
 * - 接口能力清单改为可编辑：UI 层 local state 维护，编辑 Modal 改 name/type/path/purpose。
 */
import { useEffect, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import StatusTag from '@/components/Tag';
import {
  usePojuConfig,
  useUpdateBaseUrl,
  useUpdateToken,
} from '@/hooks/useSettings';
import type { TokenStatus } from '@/api/types';

const { Title, Text } = Typography;

interface ApiAbility {
  key: string;
  name: string;
  type: 'read' | 'write';
  path: string;
  purpose: string;
}

const TYPE_LABEL: Record<ApiAbility['type'], string> = {
  read: '读',
  write: '写',
};

const TYPE_COLOR: Record<ApiAbility['type'], string> = {
  read: 'blue',
  write: 'purple',
};

const TOKEN_STATUS_KEY: Record<TokenStatus, 'normal' | 'error' | 'unknown'> = {
  valid: 'normal',
  invalid: 'error',
  unknown: 'unknown',
};

const TOKEN_STATUS_LABEL: Record<TokenStatus, string> = {
  valid: 'Token 正常',
  invalid: 'Token 失效',
  // 修复文案误导：unknown 实为「未校验」，与「未配置」是两回事
  unknown: 'Token 未校验',
};

// 接口能力清单（前端 local state；编辑 Modal 改这里，不持久化）
const DEFAULT_API_ABILITIES: ApiAbility[] = [
  {
    key: 'fetch-checkins',
    name: '拉取学员打卡记录',
    type: 'read',
    path: '/api/volunteer/checkins',
    purpose: '志愿者看板同步学员打卡数据',
  },
  {
    key: 'submit-grade',
    name: '提交作业打分',
    type: 'write',
    path: '/api/volunteer/grades',
    purpose: '志愿者评改后同步星级与评语到破局',
  },
  {
    key: 'submit-checkin',
    name: '提交打卡内容',
    type: 'write',
    path: '/api/student/checkin',
    purpose: '学员自动提交打卡四板块（降级路径）',
  },
  {
    key: 'fetch-progress',
    name: '读取训练进度',
    type: 'read',
    path: '/api/student/progress',
    purpose: '实时同步行动营进度与有效天数',
  },
];

export default function Settings() {
  const { message } = App.useApp();
  const configQuery = usePojuConfig();
  const updateToken = useUpdateToken();
  const updateBaseUrl = useUpdateBaseUrl();

  const [token, setToken] = useState<string>('');
  const [baseUrl, setBaseUrl] = useState<string>('');
  const [tokenTouched, setTokenTouched] = useState(false);
  const [urlTouched, setUrlTouched] = useState(false);

  // 接口能力清单（local state；编辑 Modal 改这里）
  const [abilities, setAbilities] = useState<ApiAbility[]>(DEFAULT_API_ABILITIES);
  const [editing, setEditing] = useState<ApiAbility | null>(null);
  const [editForm] = Form.useForm<ApiAbility>();

  // 进入页面时，用后端返回填充表单（不覆盖用户已编辑的部分）
  useEffect(() => {
    if (!configQuery.data) return;
    if (!tokenTouched) setToken('');
    if (!urlTouched) setBaseUrl(configQuery.data.base_url ?? '');
  }, [configQuery.data, tokenTouched, urlTouched]);

  const config = configQuery.data;
  const tokenStatus: TokenStatus = config?.token_status ?? 'unknown';
  const lastChecked = config?.last_checked_at;
  const hasToken = !!config?.has_token;

  const serverBaseUrl = config?.base_url ?? '';
  const baseUrlChanged = baseUrl !== serverBaseUrl;
  const tokenChanged = tokenTouched && token.length > 0;
  // 任一字段变化即可保存（不再要求「必须有 token」）
  const saveDisabled = !tokenChanged && !baseUrlChanged;

  const handleSave = async () => {
    if (saveDisabled) return;
    try {
      // 顺序：先 base_url，再 token（base_url 失败时不应继续）
      if (baseUrlChanged) {
        await updateBaseUrl.mutateAsync(baseUrl.trim() || null);
        setUrlTouched(false);
      }
      if (tokenChanged) {
        await updateToken.mutateAsync(token);
        setToken('');
        setTokenTouched(false);
      }
      message.success('配置已保存');
    } catch {
      // 全局 toast 已处理
    }
  };

  const openEdit = (a: ApiAbility) => {
    setEditing(a);
    editForm.setFieldsValue(a);
  };
  const saveEdit = async () => {
    if (!editing) return;
    try {
      const values = await editForm.validateFields();
      setAbilities((prev) =>
        prev.map((it) => (it.key === editing.key ? { ...it, ...values } : it))
      );
      setEditing(null);
      message.success('已保存（仅本地，未持久化到后端）');
    } catch {
      // 表单校验失败由 Modal 内部展示
    }
  };

  const columns: ColumnsType<ApiAbility> = [
    {
      title: '接口名',
      dataIndex: 'name',
      key: 'name',
      width: 220,
    },
    {
      title: '读写类型',
      dataIndex: 'type',
      key: 'type',
      width: 110,
      render: (type: ApiAbility['type']) => (
        <span
          style={{
            display: 'inline-block',
            minWidth: 36,
            padding: '0 10px',
            lineHeight: '20px',
            borderRadius: 10,
            fontSize: 11,
            textAlign: 'center',
            color: type === 'read' ? '#1d4ed8' : '#be185d',
            background: type === 'read' ? '#dbeafe' : '#fce7f3',
          }}
        >
          {TYPE_LABEL[type]}
        </span>
      ),
    },
    {
      title: '接口路径',
      dataIndex: 'path',
      key: 'path',
      width: 240,
      render: (p: string) => (
        <Text style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{p}</Text>
      ),
    },
    {
      title: '用途',
      dataIndex: 'purpose',
      key: 'purpose',
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, r: ApiAbility) => (
        <Button size="small" type="link" style={{ padding: 0 }} onClick={() => openEdit(r)}>
          编辑
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
          接口配置
        </Title>
        <Text style={{ color: 'var(--text-sub)', fontSize: 13 }}>
          管理破局平台 Token、连接测试与已知接口能力清单
        </Text>
      </div>

      {/* Token 配置卡 */}
      <Card
        title={<span style={{ fontSize: 14, fontWeight: 600 }}>Token 配置</span>}
        style={{
          marginBottom: 16,
          borderRadius: 10,
          background: 'var(--surface)',
        }}
        bodyStyle={{ padding: 20 }}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div>
            <div style={{ marginBottom: 6, fontSize: 13, color: 'var(--text)' }}>
              Authorization Token
            </div>
            <Input.Password
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                setTokenTouched(true);
              }}
              placeholder="Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOi...（完整 Token）"
              style={{ width: 480 }}
              autoComplete="off"
            />
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-sub)' }}>
              {hasToken
                ? `当前已配置 Token：${config?.token_masked ?? '******'}`
                : '尚未配置 Token，所有依赖破局接口的能力将自动降级'}
            </div>
          </div>

          <div>
            <div style={{ marginBottom: 6, fontSize: 13, color: 'var(--text)' }}>
              接口地址
            </div>
            <Input
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setUrlTouched(true);
              }}
              placeholder="https://api.poju.example.com（预留，后端默认地址）"
              style={{ width: 480 }}
            />
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-sub)' }}>
              MVP 预留字段，后续用于切换破局接口环境
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              borderRadius: 6,
              background: 'var(--bg)',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <span style={{ fontSize: 13, color: 'var(--text-sub)' }}>Token 状态：</span>
            <StatusTag
              status={TOKEN_STATUS_KEY[tokenStatus]}
              text={TOKEN_STATUS_LABEL[tokenStatus]}
            />
            <span style={{ fontSize: 12, color: 'var(--text-light)' }}>
              {lastChecked
                ? `上次校验：${dayjs(lastChecked).format('YYYY-MM-DD HH:mm:ss')}`
                : '尚未校验'}
            </span>
          </div>

          <Space>
            <Button
              type="primary"
              onClick={handleSave}
              loading={updateToken.isPending || updateBaseUrl.isPending}
              disabled={saveDisabled}
            >
              保存配置
            </Button>
            {/* 测试连接按钮已屏蔽：后端 /poju/test 暂时禁用，未找到合适的探测接口 */}
          </Space>

          <Alert
            type="info"
            showIcon
            message="Token 过期处理"
            description="若接口调用返回 401，请重新登录破局获取新 Token 后粘贴保存。"
            style={{ borderRadius: 6 }}
          />
        </Space>
      </Card>

      {/* 接口能力清单卡 */}
      <Card
        title={<span style={{ fontSize: 14, fontWeight: 600 }}>接口能力清单</span>}
        style={{ borderRadius: 10, background: 'var(--surface)' }}
        bodyStyle={{ padding: 20 }}
      >
        <Table<ApiAbility>
          rowKey="key"
          columns={columns}
          dataSource={abilities}
          pagination={false}
          size="middle"
        />
      </Card>

      {/* 接口能力清单编辑 Modal（local state；改后仅本页生效） */}
      <Modal
        title={`编辑接口：${editing?.name ?? ''}`}
        open={!!editing}
        onCancel={() => setEditing(null)}
        onOk={saveEdit}
        okText="保存"
        cancelText="取消"
        destroyOnClose
        maskClosable={false}
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item
            label="接口名"
            name="name"
            rules={[{ required: true, message: '请输入接口名' }]}
          >
            <Input placeholder="如：拉取学员打卡记录" />
          </Form.Item>
          <Form.Item
            label="读写类型"
            name="type"
            rules={[{ required: true, message: '请选择读写类型' }]}
          >
            <Radio.Group>
              <Radio value="read">读</Radio>
              <Radio value="write">写</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item
            label="接口路径"
            name="path"
            rules={[
              { required: true, message: '请输入接口路径' },
              { pattern: /^\//, message: '路径必须以 / 开头' },
            ]}
          >
            <Input placeholder="/api/volunteer/checkins" />
          </Form.Item>
          <Form.Item
            label="用途"
            name="purpose"
            rules={[{ required: true, message: '请输入用途说明' }]}
          >
            <Input placeholder="如：志愿者看板同步学员打卡数据" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}