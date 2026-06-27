/**
 * P10 评分标准（全局）。
 *
 * - 页头：标题 + 副标题 + 保存按钮
 * - 评分维度 Card：维度表格 + 添加/编辑/删除
 * - 星级判定规则 Card：三档规则输入
 * - 底部提示
 */
import { useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as scoringApi from '@/api/scoring';
import type { Dimension, ScoringOut, StarRules } from '@/api/types';
import { toastOnBizError } from '@/api/client';

const { Title, Text } = Typography;

// query keys（与 useScoring 配套）
export const scoringKeys = {
  all: ['scoring'] as const,
};

/** 读取评分标准（全局唯一 active） */
export function useScoring() {
  return useQuery({
    queryKey: scoringKeys.all,
    queryFn: scoringApi.getScoring,
  });
}

/** 更新评分标准 */
export function useUpdateScoring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { dimensions: Dimension[]; star_rules: StarRules }) =>
      scoringApi.updateScoring(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scoringKeys.all });
    },
    onError: (err) => {
      toastOnBizError(err);
    },
  });
}

// 默认空规则（首次进入或后端尚未写入时使用）
const DEFAULT_STAR_RULES: StarRules = {
  three: '内容详实、有思考深度与独特收获，三档最优',
  two: '记录了基本行动与收获，达到合格线',
  one: '内容空泛或明显敷衍，视为无效打卡',
};

const DEFAULT_DIMENSIONS: Dimension[] = [
  { key: 'action', name: '行动力', desc: '是否明确记录了今日的具体行动', depends_archive: false },
  { key: 'reflection', name: '反思深度', desc: '是否对执行过程进行了有效复盘', depends_archive: true },
];

interface EditDimState {
  open: boolean;
  record?: Dimension | null;
  form: Dimension;
}

/** 评分标准页面 */
export default function Scoring() {
  const { message } = App.useApp();
  const { data, isLoading } = useScoring();
  const update = useUpdateScoring();

  // 表单受控：维度（编辑态）+ 星级规则
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [starRules, setStarRules] = useState<StarRules>(DEFAULT_STAR_RULES);

  const [edit, setEdit] = useState<EditDimState>({
    open: false,
    record: null,
    form: { key: '', name: '', desc: '', depends_archive: false },
  });

  // 远端数据 → 本地编辑态
  useEffect(() => {
    if (!data) return;
    setDimensions(data.dimensions ?? []);
    setStarRules(
      data.star_rules ?? { three: DEFAULT_STAR_RULES.three, two: DEFAULT_STAR_RULES.two, one: DEFAULT_STAR_RULES.one },
    );
  }, [data]);

  const keyDup = useMemo(() => {
    const map = new Map<string, number>();
    dimensions.forEach((d) => map.set(d.key, (map.get(d.key) ?? 0) + 1));
    return map;
  }, [dimensions]);

  const dirty = useMemo(() => {
    if (!data) return false;
    if ((data.dimensions ?? []).length !== dimensions.length) return true;
    for (let i = 0; i < dimensions.length; i += 1) {
      const a = dimensions[i];
      const b = (data.dimensions ?? [])[i];
      if (
        a.key !== b.key ||
        a.name !== b.name ||
        a.desc !== b.desc ||
        Boolean(a.depends_archive) !== Boolean(b.depends_archive)
      ) {
        return true;
      }
    }
    const r0 = data.star_rules ?? DEFAULT_STAR_RULES;
    if (r0.three !== starRules.three) return true;
    if (r0.two !== starRules.two) return true;
    if (r0.one !== starRules.one) return true;
    return false;
  }, [data, dimensions, starRules]);

  // ----- 维度操作 -----
  const openAdd = () => {
    setEdit({
      open: true,
      record: null,
      form: { key: '', name: '', desc: '', depends_archive: false },
    });
  };

  const openEdit = (rec: Dimension) => {
    setEdit({
      open: true,
      record: rec,
      form: { ...rec },
    });
  };

  const submitEdit = () => {
    const f = edit.form;
    if (!f.key.trim() || !f.name.trim()) {
      message.warning('请填写维度 key 与名称');
      return;
    }
    // 唯一性校验
    const dup = dimensions.some(
      (d) => d.key === f.key.trim() && d !== edit.record,
    );
    if (dup) {
      message.warning(`维度 key「${f.key}」已存在，请换一个`);
      return;
    }
    const next: Dimension = {
      key: f.key.trim(),
      name: f.name.trim(),
      desc: f.desc.trim(),
      depends_archive: Boolean(f.depends_archive),
    };
    if (edit.record) {
      setDimensions((prev) => prev.map((d) => (d === edit.record ? next : d)));
    } else {
      setDimensions((prev) => [...prev, next]);
    }
    setEdit({ open: false, record: null, form: { key: '', name: '', desc: '', depends_archive: false } });
  };

  const removeDim = (rec: Dimension) => {
    setDimensions((prev) => prev.filter((d) => d !== rec));
  };

  // ----- 保存 -----
  const onSave = async () => {
    // 校验
    const empty = dimensions.find((d) => !d.key.trim() || !d.name.trim());
    if (empty) {
      message.warning('存在未填写完整的维度');
      return;
    }
    if (!starRules.three.trim() || !starRules.two.trim() || !starRules.one.trim()) {
      message.warning('请填写完整的星级判定规则');
      return;
    }
    try {
      const saved = (await update.mutateAsync({
        dimensions,
        star_rules: starRules,
      })) as ScoringOut;
      message.success('已保存评分标准');
      // 同步本地（mutation 已 invalidate，但本地 state 立即跟随服务端）
      setDimensions(saved.dimensions ?? []);
      setStarRules(
        saved.star_rules ?? { three: starRules.three, two: starRules.two, one: starRules.one },
      );
    } catch (err) {
      toastOnBizError(err);
    }
  };

  const columns: ColumnsType<Dimension> = [
    {
      title: 'Key',
      dataIndex: 'key',
      key: 'key',
      width: 140,
      render: (v: string) => {
        const dup = (keyDup.get(v) ?? 0) > 1;
        return (
          <Space size={6}>
            <Tag color="blue" style={{ borderRadius: 'var(--radius-sm)' }}>{v}</Tag>
            {dup ? <Tag color="error" style={{ borderRadius: 'var(--radius-sm)' }}>重复</Tag> : null}
          </Space>
        );
      },
    },
    {
      title: '维度名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: '说明',
      dataIndex: 'desc',
      key: 'desc',
      ellipsis: true,
    },
    {
      title: '依赖档案',
      dataIndex: 'depends_archive',
      key: 'depends_archive',
      width: 110,
      render: (v: boolean | undefined) =>
        v ? <Tag color="purple" style={{ borderRadius: 'var(--radius-sm)' }}>是</Tag>
           : <Tag style={{ borderRadius: 'var(--radius-sm)' }}>否</Tag>,
    },
    {
      title: '操作',
      key: 'op',
      width: 160,
      render: (_v, rec) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => openEdit(rec)}>编辑</Button>
          <Popconfirm
            title="删除该维度？"
            description="删除后将不再作为评改依据。"
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => removeDim(rec)}
          >
            <Button type="link" size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 16,
          gap: 16,
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, fontSize: 'var(--fs-title)', fontWeight: 700 }}>
            评分标准
          </Title>
          <Text type="secondary" style={{ fontSize: 'var(--fs-sub)' }}>
            配置评改依据：评分维度 + 星级判定规则。修改对后续评改生效，已评改记录不回溯重评。
          </Text>
        </div>
        <Space>
          <Button
            type="primary"
            icon={<span>💾</span>}
            onClick={onSave}
            loading={update.isPending}
            disabled={!dirty || isLoading}
          >
            保存
          </Button>
        </Space>
      </div>

      {/* 评分维度 Card */}
      <Card
        title={
          <Space>
            <span style={{ fontSize: 'var(--fs-card-title)', fontWeight: 600 }}>评分维度</span>
            <Tag style={{ borderRadius: 'var(--radius-sm)' }}>{dimensions.length} 项</Tag>
          </Space>
        }
        extra={
          <Button type="primary" ghost onClick={openAdd}>
            + 添加维度
          </Button>
        }
        style={{
          marginBottom: 16,
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
        }}
        styles={{ body: { padding: 0 } }}
      >
        <Table<Dimension>
          rowKey={(r) => `${r.key}-${r.name}`}
          dataSource={dimensions}
          columns={columns}
          pagination={false}
          loading={isLoading}
          locale={{ emptyText: '暂无维度，点击右上角「添加维度」开始配置' }}
        />
      </Card>

      {/* 星级判定规则 Card */}
      <Card
        title={
          <span style={{ fontSize: 'var(--fs-card-title)', fontWeight: 600 }}>星级判定规则</span>
        }
        style={{
          marginBottom: 16,
          borderRadius: 'var(--radius-card)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        <Form layout="vertical">
          <Form.Item
            label={
              <Space size={6}>
                <span style={{ color: 'var(--star)' }}>⭐⭐⭐</span>
                <Text strong>三星判定</Text>
                <Tag color="gold" style={{ borderRadius: 'var(--radius-sm)' }}>优秀</Tag>
              </Space>
            }
          >
            <Input
              value={starRules.three}
              onChange={(e) => setStarRules((p) => ({ ...p, three: e.target.value }))}
              placeholder="描述三星打卡的判定条件"
              maxLength={200}
            />
          </Form.Item>
          <Form.Item
            label={
              <Space size={6}>
                <span style={{ color: 'var(--star)' }}>⭐⭐</span>
                <Text strong>二星判定</Text>
                <Tag color="success" style={{ borderRadius: 'var(--radius-sm)' }}>有效</Tag>
              </Space>
            }
          >
            <Input
              value={starRules.two}
              onChange={(e) => setStarRules((p) => ({ ...p, two: e.target.value }))}
              placeholder="描述二星打卡的判定条件"
              maxLength={200}
            />
          </Form.Item>
          <Form.Item
            label={
              <Space size={6}>
                <span style={{ color: 'var(--star)' }}>⭐</span>
                <Text strong>一星判定</Text>
                <Tag color="error" style={{ borderRadius: 'var(--radius-sm)' }}>无效</Tag>
              </Space>
            }
          >
            <Input
              value={starRules.one}
              onChange={(e) => setStarRules((p) => ({ ...p, one: e.target.value }))}
              placeholder="描述一星打卡的判定条件"
              maxLength={200}
            />
          </Form.Item>
        </Form>
      </Card>

      {/* 底部提示 */}
      <div
        style={{
          padding: '10px 14px',
          background: 'var(--primary-light)',
          color: 'var(--primary)',
          border: '1px solid #c7d2fe',
          borderRadius: 'var(--radius-sm)',
          fontSize: 'var(--fs-sub)',
        }}
      >
        有效打卡 = ≥ 2 星。修改对后续评改生效，已评改记录不回溯重评。
      </div>

      {/* 维度编辑弹窗 */}
      {edit.open ? (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() =>
            setEdit({ open: false, record: null, form: { key: '', name: '', desc: '', depends_archive: false } })
          }
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: 480,
              maxWidth: '90vw',
              background: 'var(--surface)',
              borderRadius: 'var(--radius-card)',
              boxShadow: 'var(--shadow-hover)',
              padding: 20,
            }}
          >
            <div style={{ fontSize: 'var(--fs-card-title)', fontWeight: 600, marginBottom: 12 }}>
              {edit.record ? '编辑维度' : '添加维度'}
            </div>
            <Form layout="vertical">
              <Form.Item label="维度 Key（唯一）" required>
                <Input
                  value={edit.form.key}
                  disabled={Boolean(edit.record)}
                  placeholder="例：action / reflection / innovation"
                  onChange={(e) => setEdit((p) => ({ ...p, form: { ...p.form, key: e.target.value } }))}
                />
              </Form.Item>
              <Form.Item label="维度名称" required>
                <Input
                  value={edit.form.name}
                  placeholder="例：行动力"
                  onChange={(e) => setEdit((p) => ({ ...p, form: { ...p.form, name: e.target.value } }))}
                />
              </Form.Item>
              <Form.Item label="说明">
                <Input.TextArea
                  value={edit.form.desc}
                  rows={3}
                  placeholder="描述该维度的评判要点"
                  onChange={(e) => setEdit((p) => ({ ...p, form: { ...p.form, desc: e.target.value } }))}
                />
              </Form.Item>
              <Form.Item label="依赖学员档案">
                <Space>
                  <Switch
                    checked={Boolean(edit.form.depends_archive)}
                    onChange={(v) => setEdit((p) => ({ ...p, form: { ...p.form, depends_archive: v } }))}
                  />
                  <Text type="secondary" style={{ fontSize: 'var(--fs-sub)' }}>
                    开启后，AI 评改将结合该学员历史档案判断进步/原创性
                  </Text>
                </Space>
              </Form.Item>
            </Form>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <Button
                onClick={() =>
                  setEdit({ open: false, record: null, form: { key: '', name: '', desc: '', depends_archive: false } })
                }
              >
                取消
              </Button>
              <Button type="primary" onClick={submitEdit}>
                {edit.record ? '保存修改' : '添加'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}