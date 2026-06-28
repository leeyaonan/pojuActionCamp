import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Input, Popconfirm, Tooltip, message } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useDeleteCamp } from '@/hooks/useCamps';

/**
 * 删除行动营按钮（详情页顶部用）。
 *
 * 设计要点：
 * - 软删除（后端 is_deleted=True），学员打卡/评分/路线记录均保留；
 * - 用 Popconfirm + 内嵌 Input 让用户**输入营名**二次确认，避免手滑；
 * - 成功后跳回首页（/），由 useDeleteCamp 自动 invalidate 列表；
 * - 不在「进行中」营隐藏入口：测试期需要快速清场，且软删除安全。
 *
 * Props:
 * - campId:    行动营 ID
 * - campName:  当前营名（用于显示 + 让用户复述输入）
 */
export interface DeleteCampButtonProps {
  campId: number;
  campName: string;
}

export default function DeleteCampButton({ campId, campName }: DeleteCampButtonProps) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState('');
  const navigate = useNavigate();
  const deleteMut = useDeleteCamp();

  const matched = useMemo(() => typed.trim() === campName.trim(), [typed, campName]);

  const handleConfirm = async () => {
    if (!matched) return;
    try {
      await deleteMut.mutateAsync(campId);
      message.success(`已删除行动营：${campName}`);
      // 跳回首页，由列表接口自然刷新
      navigate('/', { replace: true });
    } catch {
      // 错误已由 useDeleteCamp.onError 弹 toast
    }
  };

  return (
    <Popconfirm
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setTyped(''); // 关闭时清空输入
      }}
      title={
        <div style={{ fontWeight: 600 }}>删除「{campName}」？</div>
      }
      description={
        <div style={{ width: 280 }}>
          <div style={{ fontSize: 12, color: 'var(--text-sub)', marginBottom: 8, lineHeight: 1.5 }}>
            此操作将隐藏该营及其打卡/评分数据，<strong>不会清空历史记录</strong>，可由管理员在数据库恢复。
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-sub)', marginBottom: 4 }}>
            请输入营名 <strong>{campName}</strong> 以确认：
          </div>
          <Input
            size="small"
            placeholder={campName}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            onPressEnter={handleConfirm}
            autoFocus
          />
        </div>
      }
      okText="删除"
      cancelText="取消"
      okButtonProps={{
        danger: true,
        disabled: !matched,
        loading: deleteMut.isPending,
      }}
      cancelButtonProps={{ disabled: deleteMut.isPending }}
      onConfirm={handleConfirm}
      placement="bottomRight"
    >
      <Tooltip title="软删除该营（可恢复）">
        <Button danger icon={<DeleteOutlined />}>
          删除营
        </Button>
      </Tooltip>
    </Popconfirm>
  );
}
