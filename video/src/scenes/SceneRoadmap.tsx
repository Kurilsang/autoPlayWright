import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {RailTimeline} from '../components/RailTimeline';
import {Reveal} from '../components/Reveal';
import {COLORS} from '../theme';
import {SCENES} from '../timing';

const items = [
  {
    tag: '近期',
    title: '评审 P1/P2 收口',
    desc: 'auth 加固、裸 selector 机械门禁、失败 trace 留存、xdist 并行（≤5，超限拒绝启动）、429 退避重试。',
  },
  {
    tag: '票 04',
    title: '动作原语库',
    desc: '两档制落地：语义原语（含完成判定/取证）+ 基础原语；基础原语必须以 assert 收口，收集期静态检查。',
  },
  {
    tag: '票 07',
    title: 'AI 生成器（opencode skill）',
    desc: '快照 + 业务描述 → flow 草稿 diff，人工评审入库；失败修复也走 diff 流，AI 只修资产、不改现场。',
  },
  {
    tag: '票 08',
    title: '快照 diff 影响分析',
    desc: '页面改版后重爬比对，输出受影响的定位器 / 页面 / flow 清单——直接圈定「这次要修哪些用例」。',
  },
  {
    tag: '扩量',
    title: '核心链路 20~50 条',
    desc: '多轮上下文漂移链路优先；远期接入 LLM-as-Judge（只评结构化维度，措辞评分走旁路不挡门禁）。',
  },
];

const milestones = ['M0 骨架 ✓', 'M1 核心链路覆盖', 'M2 AI 生成流水线', 'M3 diff / Judge'];

export const SceneRoadmap: React.FC = () => {
  return (
    <SceneShell
      chapter={SCENES[5].chapter}
      title="之后的打算"
      subtitle="顺序已排定：先把稳定性和门禁收口，再上生成器，最后才是影响分析与判定。"
      duration={SCENES[5].duration}
    >
      <RailTimeline items={items} startDelay={18} stepDelay={42} />
      <Reveal delay={280} y={20}>
        <div
          style={{
            marginTop: 30,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <div style={{fontSize: 21, fontWeight: 800, color: COLORS.faint}}>
            里程碑
          </div>
          {milestones.map((m, i) => (
            <React.Fragment key={m}>
              <div
                style={{
                  fontSize: 21,
                  fontWeight: 700,
                  color: i === 0 ? COLORS.accent2 : COLORS.dim,
                  background:
                    i === 0 ? 'rgba(55,214,166,0.12)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${i === 0 ? 'rgba(55,214,166,0.4)' : COLORS.border}`,
                  borderRadius: 999,
                  padding: '9px 20px',
                }}
              >
                {m}
              </div>
              {i < milestones.length - 1 ? (
                <div style={{color: COLORS.faint, fontSize: 20}}>→</div>
              ) : null}
            </React.Fragment>
          ))}
        </div>
      </Reveal>
    </SceneShell>
  );
};
