import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {BulletList} from '../components/Bits';
import {Reveal} from '../components/Reveal';
import {COLORS} from '../theme';
import {SCENES} from '../timing';

const left = [
  {
    text: 'LLM-as-Judge 的判定实现',
    sub: '只预留 schema 字段与接口形状，判定逻辑后置接入',
    tone: 'bad' as const,
  },
  {
    text: '全自动探索式测试',
    sub: 'AI 不自主漫游页面；生成物必须人工评审后才入库（D2/D10）',
    tone: 'bad' as const,
  },
  {
    text: '后端接口测试 / 造数、性能压测',
    sub: '只测 UI 的外部行为，接口与性能各有专门手段',
    tone: 'bad' as const,
  },
  {
    text: '视觉像素级回归、移动端',
    sub: '覆盖目标是 Web + Electron 两端，不做像素比对',
    tone: 'bad' as const,
  },
];

const right = [
  {
    text: 'mock LLM 后端',
    sub: 'Agent 产品必须测真实链路，mock 出来的绿灯没有意义',
    tone: 'bad' as const,
  },
  {
    text: '测试平台 / 看板本体',
    sub: '框架只负责输出标准 JSON，消费端交给内部平台',
    tone: 'bad' as const,
  },
  {
    text: '手工用例 ↔ 自动化用例的管理映射系统',
    sub: '不做用例管理平台，用例即仓库里的 YAML 文件',
    tone: 'bad' as const,
  },
];

export const SceneNotSolves: React.FC = () => {
  return (
    <SceneShell
      chapter={SCENES[3].chapter}
      title="它明确不解决什么"
      subtitle="边界先说清楚——这些都写进了 SPEC 的 Out of Scope，不承诺、不兜底。"
      duration={SCENES[3].duration}
    >
      <div style={{display: 'flex', gap: 56}}>
        <div style={{flex: 1, minWidth: 0}}>
          <BulletList items={left} startDelay={16} step={30} fontSize={25} gap={22} />
        </div>
        <div style={{flex: 1, minWidth: 0}}>
          <BulletList items={right} startDelay={32} step={30} fontSize={25} gap={22} />
        </div>
      </div>
      <Reveal delay={190} y={22}>
        <div
          style={{
            marginTop: 40,
            background: 'rgba(255,107,122,0.10)',
            border: '1px solid rgba(255,107,122,0.35)',
            borderRadius: 16,
            padding: '22px 30px',
            fontSize: 27,
            lineHeight: 1.55,
            fontWeight: 650,
          }}
        >
          定位：链路回归资产，不是测试体系的全部。
          <span style={{color: COLORS.dim, fontWeight: 500}}>
            {' '}
            只做「确定性、可复用、可判信」的那一层，其余交给对应领域的专门工具。
          </span>
        </div>
      </Reveal>
    </SceneShell>
  );
};
