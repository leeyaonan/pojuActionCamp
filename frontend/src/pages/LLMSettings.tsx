/**
 * AI 模型配置页。
 *
 * 结构（对齐 docs/llm-settings/03-UI方案.md）：
 * - 页头：标题"AI 模型配置"
 * - 当前使用卡：展示当前激活厂商 / .env 兜底 / 无配置
 * - 厂商配置卡：表格（厂商/协议/接入地址/模型/Key状态/激活/操作）+ 新增按钮 + 编辑 Modal
 * - 说明卡：激活说明 + Key 加密提示
 *
 * 复用 Settings.tsx 的视觉范式（卡片 / StatusTag / Input.Password / 测试连接交互）。
 */
import { useState } from 'react';
import {
  Alert,
  App,
  AutoComplete,
  Button,
  Card,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import StatusTag from '@/components/Tag';
import {
  useActivateProvider,
  useCreateProvider,
  useDeleteProvider,
  useLLMActive,
  useLLMProviders,
  useTestProvider,
  useUpdateProvider,
} from '@/hooks/useLLMSettings';
import type {
  LlmProtocol,
  LlmProviderOut,
  LlmProviderUpdate,
  TokenStatus,
} from '@/api/types';

const { Title, Text } = Typography;

const PROTOCOL_OPTIONS = [
  { value: 'openai_compatible', label: 'OpenAI 兼容' },
  { value: 'anthropic', label: 'Anthropic 兼容' },
];

const PROTOCOL_LABEL: Record<LlmProtocol, string> = {
  openai_compatible: 'OpenAI 兼容',
  anthropic: 'Anthropic 兼容',
};

/** Key 状态徽标：valid→可用 / invalid→失效 / unknown 且无 key→未配置 / unknown 且有 key→待测试 */
function KeyStatusTag({ p }: { p: LlmProviderOut }) {
  if (p.key_status === 'valid') return <StatusTag status="normal" text="可用" />;
  if (p.key_status === 'invalid') return <StatusTag status="error" text="失效" />;
  if (!p.has_api_key) return <StatusTag status="unknown" text="未配置" />;
  return <StatusTag status="pending" text="待测试" />;
}

/** 激活状态徽标 */
function ActiveStatusTag({ status }: { status: TokenStatus }) {
  if (status === 'valid') return <StatusTag status="normal" text="可用" />;
  if (status === 'invalid') return <StatusTag status="error" text="失效" />;
  return <StatusTag status="unknown" text="待测试" />;
}

export default function LLMSettings() {
  const { message } = App.useApp();
  const providersQuery = useLLMProviders();
  const activeQuery = useLLMActive();
  const createMut = useCreateProvider();
  const updateMut = useUpdateProvider();
  const deleteMut = useDeleteProvider();
  const testMut = useTestProvider();
  const activateMut = useActivateProvider();

  // 编辑/新增 Modal 状态
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingPreset, setEditingPreset] = useState(false);
  const [editingMasked, setEditingMasked] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [protocol, setProtocol] = useState<LlmProtocol>('openai_compatible');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [apiKey, setApiKey] = useState('');

  // per-row loading
  const [testId, setTestId] = useState<number | null>(null);
  const [activateId, setActivateId] = useState<number | null>(null);

  const providers = providersQuery.data ?? [];

  const openCreate = () => {
    setModalMode('create');
    setEditingId(null);
    setEditingPreset(false);
    setEditingMasked(null);
    setName('');
    setProtocol('openai_compatible');
    setBaseUrl('');
    setModel('');
    setModels([]);
    setApiKey('');
    setModalOpen(true);
  };

  const openEdit = (p: LlmProviderOut) => {
    setModalMode('edit');
    setEditingId(p.id);
    setEditingPreset(p.is_preset);
    setEditingMasked(p.api_key_masked ?? null);
    setName(p.name);
    setProtocol(p.protocol);
    setBaseUrl(p.base_url);
    setModel(p.model);
    setModels(p.models ?? []);
    setApiKey('');
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!name.trim()) {
      message.warning('请填写厂商名称');
      return;
    }
    if (!baseUrl.trim()) {
      message.warning('请填写接入地址');
      return;
    }
    if (!model.trim()) {
      message.warning('请填写模型名');
      return;
    }
    try {
      if (modalMode === 'create') {
        await createMut.mutateAsync({
          name: name.trim(),
          protocol,
          base_url: baseUrl.trim(),
          model: model.trim(),
          models: models.length ? models : null,
          api_key: apiKey || null,
        });
        message.success('已新增厂商');
      } else {
        const payload: LlmProviderUpdate = {
          name: name.trim(),
          protocol,
          base_url: baseUrl.trim(),
          model: model.trim(),
          models: models,
          // api_key 留空不传（None=不修改）；填了才传
          ...(apiKey ? { api_key: apiKey } : {}),
        };
        await updateMut.mutateAsync({ id: editingId!, payload });
        message.success('已保存');
      }
      setModalOpen(false);
    } catch {
      // 全局 toast 已处理
    }
  };

  const handleTest = async (p: LlmProviderOut) => {
    setTestId(p.id);
    try {
      const r = await testMut.mutateAsync(p.id);
      if (r.valid) message.success(r.message || '连接成功');
      else message.error(r.message || '连接失败');
    } catch {
      // 全局 toast 已处理
    } finally {
      setTestId(null);
    }
  };

  const handleActivate = async (p: LlmProviderOut) => {
    setActivateId(p.id);
    try {
      await activateMut.mutateAsync(p.id);
      message.success(`已切换到 ${p.name}`);
    } catch {
      // 全局 toast 已处理
    } finally {
      setActivateId(null);
    }
  };

  const handleDelete = async (p: LlmProviderOut) => {
    try {
      await deleteMut.mutateAsync(p.id);
      message.success('已删除');
    } catch {
      // 全局 toast 已处理
    }
  };

  const columns: ColumnsType<LlmProviderOut> = [
    {
      title: '厂商',
      dataIndex: 'name',
      key: 'name',
      width: 140,
      render: (n: string, r: LlmProviderOut) => (
        <Space size={4}>
          <span>{n}</span>
          {r.is_preset && (
            <Tag color="blue" style={{ margin: 0 }}>
              预置
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: '协议',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 140,
      render: (p: LlmProtocol) => PROTOCOL_LABEL[p],
    },
    {
      title: '接入地址',
      dataIndex: 'base_url',
      key: 'base_url',
      width: 280,
      ellipsis: true,
      render: (u: string) => <Tooltip title={u}><span>{u}</span></Tooltip>,
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
      width: 160,
    },
    {
      title: 'Key 状态',
      key: 'key_status',
      width: 110,
      render: (_, r) => <KeyStatusTag p={r} />,
    },
    {
      title: '激活',
      key: 'is_active',
      // 必须加 dataIndex：否则 render 第 1 参数是 record 对象（永远 truthy），
      // 会恒走「当前」分支、激活按钮永不渲染
      dataIndex: 'is_active',
      width: 90,
      render: (active: boolean, r: LlmProviderOut) =>
        active ? (
          <Tag color="green">当前</Tag>
        ) : (
          <Button
            size="small"
            type="link"
            style={{ padding: 0 }}
            loading={activateMut.isPending && activateId === r.id}
            disabled={r.key_status !== 'valid'}
            onClick={() => handleActivate(r)}
          >
            激活
          </Button>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, r: LlmProviderOut) => (
        <Space size={0}>
          <Button size="small" type="link" style={{ padding: 0 }} onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Button
            size="small"
            type="link"
            style={{ padding: 0 }}
            loading={testMut.isPending && testId === r.id}
            onClick={() => handleTest(r)}
          >
            测试
          </Button>
          {!r.is_preset && (
            <Popconfirm
              title={
                r.is_active
                  ? `确认删除 ${r.name}？该厂商当前已激活，删除后将回退到 .env 配置`
                  : `确认删除 ${r.name}？`
              }
              onConfirm={() => handleDelete(r)}
              okText="删除"
              cancelText="取消"
            >
              <Button size="small" type="link" danger style={{ padding: 0 }}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const active = activeQuery.data;

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
          AI 模型配置
        </Title>
        <Text style={{ color: 'var(--text-sub)', fontSize: 13 }}>
          管理大模型厂商 Key、测试连接与激活切换
        </Text>
      </div>

      {/* 当前使用卡 */}
      <Card
        title={<span style={{ fontSize: 14, fontWeight: 600 }}>当前使用</span>}
        style={{ marginBottom: 16, borderRadius: 10, background: 'var(--surface)' }}
        bodyStyle={{ padding: 20 }}
      >
        {activeQuery.isLoading ? (
          <Spin />
        ) : active?.source === 'db' ? (
          <Space wrap>
            <span style={{ fontSize: 13 }}>当前使用厂商：</span>
            <Text strong>{active.name}</Text>
            <Text style={{ color: 'var(--text-sub)' }}>（{active.model}）</Text>
            <ActiveStatusTag status={active.key_status} />
            {active.last_checked_at && (
              <Text style={{ fontSize: 12, color: 'var(--text-light)' }}>
                上次校验：{dayjs(active.last_checked_at).format('YYYY-MM-DD HH:mm:ss')}
              </Text>
            )}
          </Space>
        ) : active?.source === 'env' ? (
          <Alert
            type="warning"
            showIcon
            message="未激活任何大模型厂商，AI 能力不可用。请在下方配置并激活一家厂商。"
          />
        ) : (
          <Alert
            type="error"
            showIcon
            message="未激活任何大模型厂商，AI 能力不可用。请在下方配置并激活一家厂商。"
          />
        )}
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-sub)' }}>
          激活后立即生效，所有 AI 能力（学习路线 / 打卡生成 / 作业评改）将调用该厂商。
        </div>
      </Card>

      {/* 厂商配置卡 */}
      <Card
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>厂商配置</span>
            <Button type="primary" size="small" onClick={openCreate}>
              新增厂商
            </Button>
          </div>
        }
        style={{ marginBottom: 16, borderRadius: 10, background: 'var(--surface)' }}
        bodyStyle={{ padding: 20 }}
      >
        <Table<LlmProviderOut>
          rowKey="id"
          columns={columns}
          dataSource={providers}
          pagination={false}
          size="middle"
          loading={providersQuery.isLoading}
          onRow={(r) => ({
            style: r.is_active ? { background: 'var(--bg)' } : {},
          })}
        />
      </Card>

      {/* 说明卡 */}
      <Card style={{ borderRadius: 10, background: 'var(--surface)' }} bodyStyle={{ padding: 16 }}>
        <Alert
          type="info"
          showIcon
          message="说明"
          description="激活后立即生效，所有 AI 能力（学习路线 / 打卡生成 / 作业评改）将调用该厂商。API Key 加密存储，仅展示末 4 位。预置 4 家厂商的接入地址与模型名来自官方文档，可在编辑中修改。LongCat 走 Anthropic 协议，其余走 OpenAI 兼容协议。"
        />
      </Card>

      {/* 编辑/新增 Modal */}
      <Modal
        title={modalMode === 'create' ? '新增厂商' : `编辑 ${name}`}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createMut.isPending || updateMut.isPending}
        okText="保存"
        cancelText="取消"
        width={560}
        destroyOnClose
      >
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <div>
            <div style={{ marginBottom: 6, fontSize: 13 }}>厂商名称</div>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：DeepSeek"
              disabled={editingPreset}
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <div style={{ marginBottom: 6, fontSize: 13 }}>接入协议</div>
            <Select
              value={protocol}
              onChange={(v) => setProtocol(v)}
              options={PROTOCOL_OPTIONS}
              style={{ width: '100%' }}
              disabled={editingPreset}
            />
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-sub)' }}>
              OpenAI 兼容：DeepSeek / GLM / MiniMax；Anthropic 兼容：LongCat
            </div>
          </div>

          <div>
            <div style={{ marginBottom: 6, fontSize: 13 }}>接入地址（base_url）</div>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.deepseek.com"
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <div style={{ marginBottom: 6, fontSize: 13 }}>模型</div>
            <AutoComplete
              value={model}
              onChange={(v) => setModel(v)}
              options={(models ?? []).map((m) => ({ value: m }))}
              placeholder="选择或输入模型名"
              style={{ width: '100%' }}
              filterOption={(input, option) =>
                (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </div>

          <div>
            <div style={{ marginBottom: 6, fontSize: 13 }}>可选模型列表</div>
            <Select
              mode="tags"
              value={models}
              onChange={(v) => setModels(v)}
              placeholder="维护该厂商支持的模型（供上方模型下拉选择）"
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <div style={{ marginBottom: 6, fontSize: 13 }}>API Key</div>
            <Input.Password
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="粘贴该厂商的 API Key"
              autoComplete="off"
              style={{ width: '100%' }}
            />
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-sub)' }}>
              {modalMode === 'edit' && editingMasked
                ? `当前：${editingMasked}，留空表示不修改`
                : '明文传输并加密存储，仅展示末 4 位'}
            </div>
          </div>
        </Space>
      </Modal>
    </div>
  );
}
