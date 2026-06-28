/**
 * P11 接口配置。
 *
 * 结构（对齐 design.md P11）：
 * - 页头：标题"接口配置"
 * - Token 配置卡：
 *   - Authorization Token Input.Password（占位"手动登录破局后，从浏览器复制 Token"）+ 提示
 *   - 接口地址 Input（预留）
 *   - Token 状态展示（valid/invalid/unknown badge + 上次校验时间）
 *   - "保存配置" + "测试连接"按钮
 * - 接口能力清单卡：表格（接口名/读写类型 badge/用途/状态 badge）
 */
import { useEffect, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Input,
  Space,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import StatusTag from '@/components/Tag';
import {
  usePojuConfig,
  useTestConnection,
  useUpdateBaseUrl,
  useUpdateToken,
} from '@/hooks/useSettings';
import type { TokenStatus } from '@/api/types';

const { Title, Text } = Typography;

interface ApiAbility {
  key: string;
  name: string;
  type: 'read' | 'write';
  purpose: string;
  status: 'verified' | 'pending';
}

const API_ABILITIES: ApiAbility[] = [
  {
    key: 'fetch-checkins',
    name: '拉取学员打卡记录',
    type: 'read',
    purpose: '志愿者看板同步学员打卡数据',
    status: 'verified',
  },
  {
    key: 'submit-grade',
    name: '提交作业打分',
    type: 'write',
    purpose: '志愿者评改后同步星级与评语到破局',
    status: 'verified',
  },
  {
    key: 'submit-checkin',
    name: '提交打卡内容',
    type: 'write',
    purpose: '学员自动提交打卡四板块（降级路径）',
    status: 'pending',
  },
  {
    key: 'fetch-progress',
    name: '读取训练进度',
    type: 'read',
    purpose: '实时同步行动营进度与有效天数',
    status: 'pending',
  },
];

const TOKEN_STATUS_KEY: Record<TokenStatus, 'normal' | 'error' | 'unknown'> = {
  valid: 'normal',
  invalid: 'error',
  unknown: 'unknown',
};

const TOKEN_STATUS_LABEL: Record<TokenStatus, string> = {
  valid: 'Token 正常',
  invalid: 'Token 失效',
  unknown: 'Token 未配置',
};

const TYPE_LABEL: Record<ApiAbility['type'], string> = {
  read: '读',
  write: '写',
};

const TYPE_COLOR: Record<ApiAbility['type'], string> = {
  read: 'blue',
  write: 'purple',
};

const STATUS_LABEL: Record<ApiAbility['status'], string> = {
  verified: '已验证',
  pending: '待确认',
};

const STATUS_TAG: Record<ApiAbility['status'], 'valid' | 'unknown'> = {
  verified: 'valid',
  pending: 'unknown',
};

export default function Settings() {
  const { message } = App.useApp();
  const configQuery = usePojuConfig();
  const updateToken = useUpdateToken();
  const updateBaseUrl = useUpdateBaseUrl();
  const testConnection = useTestConnection();

  const [token, setToken] = useState<string>('');
  const [baseUrl, setBaseUrl] = useState<string>('');
  const [tokenTouched, setTokenTouched] = useState(false);
  const [urlTouched, setUrlTouched] = useState(false);

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

  const handleSave = async () => {
    if (!token) {
      message.warning('请先粘贴 Token 再保存');
      return;
    }
    try {
      // 顺序：先 base_url，再 token（base_url 失败时不应继续）
      const serverBaseUrl = config?.base_url ?? '';
      if (baseUrl !== serverBaseUrl) {
        await updateBaseUrl.mutateAsync(baseUrl.trim() || null);
      }
      await updateToken.mutateAsync(token);
      message.success('配置已保存');
      setToken('');
      setTokenTouched(false);
    } catch {
      // 全局 toast 已处理
    }
  };

  const handleTest = async () => {
    try {
      const result = await testConnection.mutateAsync();
      if (result.valid) {
        message.success(result.message || '连接成功');
      } else {
        message.error(result.message || '连接失败');
      }
    } catch {
      // 全局 toast 已处理
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
      title: '用途',
      dataIndex: 'purpose',
      key: 'purpose',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: ApiAbility['status']) => (
        <StatusTag status={STATUS_TAG[status]} text={STATUS_LABEL[status]} />
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
              placeholder="手动登录破局后，从浏览器复制 Token"
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
              disabled={!token}
            >
              保存配置
            </Button>
            <Button
              onClick={handleTest}
              loading={testConnection.isPending}
              disabled={!hasToken}
            >
              测试连接
            </Button>
          </Space>

          <Alert
            type="info"
            showIcon
            message="Token 过期处理"
            description="若接口返回 401，请重新登录破局获取 Token 后粘贴保存；测试连接会立即校验当前 Token 有效性。"
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
          dataSource={API_ABILITIES}
          pagination={false}
          size="middle"
          loading={configQuery.isLoading}
        />
      </Card>
    </div>
  );
}