import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {Reveal} from '../components/Reveal';
import {COLORS} from '../theme';
import {SCENES} from '../timing';

const panels: {
  title: string;
  tag: string;
  tone: string;
  items: string[];
}[] = [
  {
    title: '框架本体',
    tag: 'src/apw',
    tone: COLORS.accent,
    items: [
      'dsl：pydantic schema，收集期校验非法 DSL',
      'engine：FlowRunner → StepEvent 事件流',
      'pages + locators：语义原语 + 定位器仓库',
      'driver：Web / Electron 统一输出 Page',
      'reporter：JSON → report.html；pytest 插件 + crawler + sanitize',
    ],
  },
  {
    title: '业务用例',
    tag: 'flows/',
    tone: COLORS.accent2,
    items: [
      '13 条链路入库：会话、并行切换、广场、样式库、操练场、桌面端对话冒烟',
      '工作流 4 条：手写保存运行 / AI 生成运行',
      '并发 2 个 AI 生成任务 / 并发 2 个 AI 运行任务',
      '并发 UI 逐标签身份核对，串台/卡死判 fail',
      '真实环境 3 次绿跑，冒烟持续绿灯',
    ],
  },
  {
    title: '运行产物',
    tag: 'reports/',
    tone: COLORS.violet,
    items: [
      'flow 级 JSON：输入/输出/断言明细/耗时/截图',
      'run 汇总：三态 passed/failed/skipped + 跳过原因',
      'report.html：单文件零依赖，会话结束自动渲染',
      'capture_context：用户输入/推理/思考/最终答案',
      '失败含取证包：归因 + 复现 + 信号时间线 + 冻结截图',
    ],
  },
  {
    title: '生成侧资产与门禁',
    tag: 'crawler + tests',
    tone: COLORS.warn,
    items: [
      '状态化爬虫 + page: probe 探查原语',
      '快照骨架：状态路径标注 + 定位器候选',
      '落盘自动脱敏：映射表 + 通用模式兜底',
      'tests 全绿；tests/test_no_secrets.py 红线门禁',
      '文档：docs/SPEC.md（25 条决策记录）+ AGENTS.md',
    ],
  },
];

export const SceneDeliverables: React.FC = () => {
  return (
    <SceneShell
      chapter={SCENES[7].chapter}
      title="交付成果长什么样"
      subtitle="代码、用例、报告、生成侧资产与门禁——四块都已落库，可持续演进。"
      duration={SCENES[7].duration}
    >
      <div style={{display: 'flex', gap: 26}}>
        {panels.slice(0, 2).map((p, i) => (
          <Reveal key={p.title} delay={16 + i * 26} y={26} style={{flex: 1}}>
            <Panel {...p} />
          </Reveal>
        ))}
      </div>
      <div style={{display: 'flex', gap: 26, marginTop: 26}}>
        {panels.slice(2).map((p, i) => (
          <Reveal key={p.title} delay={76 + i * 26} y={26} style={{flex: 1}}>
            <Panel {...p} />
          </Reveal>
        ))}
      </div>
      <Reveal delay={150} y={20}>
        <div
          style={{
            marginTop: 26,
            background: 'rgba(91,140,255,0.12)',
            border: '1px solid rgba(91,140,255,0.4)',
            borderRadius: 16,
            padding: '22px 30px',
            fontSize: 28,
            lineHeight: 1.5,
            fontWeight: 700,
          }}
        >
          最小可交付形态：新增一条核心链路{' '}
          <span style={{color: COLORS.accent2}}>≈ 写/审一个 YAML 文件</span>——这就是
          README 里承诺的生产闭环。
        </div>
      </Reveal>
    </SceneShell>
  );
};

const Panel: React.FC<{
  title: string;
  tag: string;
  tone: string;
  items: string[];
}> = ({title, tag, tone, items}) => (
  <div
    style={{
      height: 300,
      background: COLORS.panel,
      border: `1px solid ${COLORS.border}`,
      borderTop: `5px solid ${tone}`,
      borderRadius: 18,
      padding: '22px 26px',
      boxSizing: 'border-box',
    }}
  >
    <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
      <div style={{fontSize: 29, fontWeight: 800}}>{title}</div>
      <span
        style={{
          fontSize: 18,
          fontFamily: "'Cascadia Code', Consolas, monospace",
          color: tone,
          border: `1px solid ${tone}66`,
          background: 'rgba(255,255,255,0.05)',
          borderRadius: 8,
          padding: '3px 11px',
        }}
      >
        {tag}
      </span>
    </div>
    <div style={{marginTop: 14}}>
      {items.map((it) => (
        <div
          key={it}
          style={{
            display: 'flex',
            gap: 11,
            fontSize: 20,
            lineHeight: 1.5,
            color: COLORS.dim,
            marginBottom: 9,
          }}
        >
          <span style={{color: tone, fontWeight: 800}}>·</span>
          <span>{it}</span>
        </div>
      ))}
    </div>
  </div>
);
