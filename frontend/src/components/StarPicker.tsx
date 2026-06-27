import { Rate } from 'antd';
import { StarFilled, StarOutlined } from '@ant-design/icons';
import { useMemo } from 'react';

/**
 * StarPicker：星级选择器（1-3 星）。
 *
 * - 默认 3 颗星，点击切换选中状态（支持清除）。
 * - 使用 AntD Rate，但限制最大 3。
 * - 颜色对齐 design.md --star (#f59e0b)。
 */
interface Props {
  value?: number;
  onChange?: (v: number | undefined) => void;
  disabled?: boolean;
  allowClear?: boolean;
}

export default function StarPicker({ value, onChange, disabled, allowClear = true }: Props) {
  // AntD Rate 用字符/Icon 都能渲染；这里用 StarFilled / StarOutlined 让颜色统一为金色
  const icons = useMemo(
    () => ({
      full: <StarFilled style={{ color: '#f59e0b', fontSize: 22 }} />,
      empty: <StarOutlined style={{ color: '#d1d5db', fontSize: 22 }} />,
    }),
    []
  );

  return (
    <Rate
      value={value ?? 0}
      onChange={(v) => onChange?.(v === 0 ? undefined : v)}
      count={3}
      character={(props) => {
        const idx = props.index ?? 0;
        return idx < (value ?? 0) ? icons.full : icons.empty;
      }}
      disabled={disabled}
      allowClear={allowClear}
    />
  );
}