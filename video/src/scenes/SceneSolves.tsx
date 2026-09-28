import React from 'react';
import {SceneShell} from '../components/SceneShell';
import {BulletList, Chip, Card} from '../components/Bits';
import {CodeCard} from '../components/CodeCard';
import {Reveal} from '../components/Reveal';
import {SCENES} from '../timing';

const solves = [
  {
    text: '新增用例 ≈ 写/审一个 YAML',
    sub: '业务链路用 DSL 描述（导航→输入→发送→断言），不写 Python 代码',
  },
  {
    text: '一次编写，双端执行',
    sub: 'Web / Electron 共享同一套 Page Object，platforms 字段控制生效矩阵',
  },
  {
    text: '改版不怕：定位器仓库',
    sub: '命名定位器多候选回退：testid > role+name > placeholder/label > text > css/xpath',
  },
  {
    text: '断言不抖：只测确定性内容',
    sub: '组件 / 状态 / 结构；「完整回答六信号」判完才断言，不再因 LLM 措辞假失败',
  },
  {
    text: '失败即取证，禁止自愈',
    sub: '归因分类 + 复现 + 信号时间线 + 冻结截图入报告，缺陷不被重试跑绿',
  },
  {
    text: '结果可消费',
    sub: '步骤级 JSON（机器/看板）+ 单文件 HTML 报告（人）+ Allure 可选',
  },
  {
    text: 'AI 半自动生成',
    sub: '爬虫快照 → LLM 草稿 → 人工评审入库 → CI 稳定回放',
  },
];

const codeLines: {text: string; tone?: 'plain' | 'key' | 'str' | 'dim'}[] = [
  {text: 'meta: { id: example-chat, platforms: [web], tags: [P0] }', tone: 'plain'},
  {text: 'steps:', tone: 'key'},
  {text: '  - do: { page: agent_chat, action: send_message,', tone: 'plain'},
  {text: '        args: { text: "你好，夹具" } }', tone: 'str'},
  {text: '  - do: { page: agent_chat, action: wait_reply_done }', tone: 'plain'},
  {text: '  - do: { page: agent_chat, action: capture_context }', tone: 'plain'},
  {text: '  - assert: { type: visible, target: message_list }', tone: 'key'},
  {text: '  - assert: { type: text_contains,', tone: 'key'},
  {text: '        target: message_list, expected: "你好，夹具" }', tone: 'str'},
  {text: '  - judge: { note: "v1 预留" }', tone: 'dim'},
];

export const SceneSolves: React.FC = () => {
  return (
    <SceneShell
      chapter={SCENES[2].chapter}
      title="它解决什么？"
      subtitle="一句话：把「逐条写代码」压缩成「写/审一个 YAML」，并且让结果可信、可追溯。"
      duration={SCENES[2].duration}
    >
      <div style={{display: 'flex', gap: 46, alignItems: 'flex-start'}}>
        <div style={{flex: 1.25, minWidth: 0}}>
          <BulletList items={solves} startDelay={18} step={26} fontSize={25} gap={17} />
        </div>
        <div style={{flex: 1, minWidth: 0}}>
          <CodeCard
            title="flows/example_chat.yaml"
            lines={codeLines}
            startDelay={40}
            lineStep={9}
            caption="一条链路 = 一个 YAML；pytest 自动收集，无需注册代码。"
          />
          <Reveal delay={200} y={20}>
            <div style={{marginTop: 18}}>
              <Card
                badge="闭环"
                tone="good"
                title="生产闭环"
                body="写 YAML → schema 校验 → pytest 解释执行 → JSON/HTML 报告 → 失败取证回流修复。"
              />
            </div>
          </Reveal>
          <Reveal delay={230} y={16}>
            <div style={{marginTop: 16, display: 'flex', gap: 12, flexWrap: 'wrap'}}>
              <Chip label="JSON 第一公民" tone="accent" fontSize={19} />
              <Chip label="report.html 零依赖" tone="good" fontSize={19} />
              <Chip label="Allure 可选" tone="default" fontSize={19} />
            </div>
          </Reveal>
        </div>
      </div>
    </SceneShell>
  );
};
