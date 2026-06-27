import { Tag as AntTag } from 'antd';

/**
 * 通用状态 Tag 组件（对齐 design.md 第七章状态徽章）。
 *
 * - pending → 橙色（待评改 / 已提交待评改 / 待办）
 * - valid   → 绿色（有效打卡 / 已评改·有效 / 正常）
 * - invalid → 红色（无效打卡 / 失效）
 * - ongoing → 绿色（进行中）
 * - ended   → 灰色（已结束）
 * - not_started → 灰色（未开始）
 * - insufficient → 红色（打卡不足）
 * - graded → 绿色（已评改）
 * - unknown → 灰色（待确认 / Token 未配）
 */
export type StatusKey =
  | 'pending'
  | 'valid'
  | 'invalid'
  | 'ongoing'
  | 'ended'
  | 'not_started'
  | 'insufficient'
  | 'graded'
  | 'qualified'
  | 'unqualified'
  | 'unknown'
  | 'normal'
  | 'warn'
  | 'error'
  | 'info';

interface Props {
  status: StatusKey;
  text?: string;
}

const COLOR_MAP: Record<StatusKey, { color: string; defaultText: string }> = {
  pending: { color: 'orange', defaultText: '待评改' },
  valid: { color: 'green', defaultText: '有效' },
  invalid: { color: 'red', defaultText: '无效' },
  ongoing: { color: 'green', defaultText: '进行中' },
  ended: { color: 'default', defaultText: '已结束' },
  not_started: { color: 'default', defaultText: '未开始' },
  insufficient: { color: 'red', defaultText: '打卡不足' },
  graded: { color: 'green', defaultText: '已评改' },
  qualified: { color: 'green', defaultText: '已达标' },
  unqualified: { color: 'red', defaultText: '未达标' },
  unknown: { color: 'default', defaultText: '待确认' },
  normal: { color: 'green', defaultText: '正常' },
  warn: { color: 'orange', defaultText: '警告' },
  error: { color: 'red', defaultText: '异常' },
  info: { color: 'blue', defaultText: '信息' },
};

export default function StatusTag({ status, text }: Props) {
  const cfg = COLOR_MAP[status];
  return <AntTag color={cfg.color}>{text ?? cfg.defaultText}</AntTag>;
}