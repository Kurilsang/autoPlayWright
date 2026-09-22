"""pytest 集成：flows/*.yaml 自动收集为测试项 + 运行时装配。

运行时（driver/repo/pages/reporter）惰性创建、进程内单例：
flow 测试项与框架自测 fixtures 共用同一实例，session 结束统一清理。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pytest import StashKey


def pytest_addoption(parser):
    group = parser.getgroup("apw")
    group.addoption(
        "--apw-env", default="fixture",
        help="执行环境名（configs/envs/<env>.yaml），默认 fixture 本地夹具站点",
    )
    group.addoption(
        "--apw-flows-dir", default="flows", help="业务链路 DSL 目录"
    )
    group.addoption(
        "--apw-reports-dir", default="reports", help="JSON 报告输出目录"
    )


# ---------- 运行时（惰性单例） ----------


@dataclass
class ApwRuntime:
    env: Any
    driver: Any
    repo: Any
    pages: Any
    reporter: Any


_RUNTIME_KEY: StashKey[ApwRuntime | None] = StashKey()


def get_runtime(config) -> ApwRuntime:
    rt = config.stash.get(_RUNTIME_KEY, None)
    if rt is not None:
        return rt

    from apw.config import load_env
    from apw.driver.app_driver import AppDriver
    from apw.engine.registry import default_registry
    from apw.locators.repo import LocatorRepo
    from apw.reporter.json_report import JsonReporter

    env = load_env(config.getoption("--apw-env"))
    driver = AppDriver(env=env)
    driver.start()
    rt = ApwRuntime(
        env=env,
        driver=driver,
        repo=LocatorRepo.load(Path("locators")),
        pages=default_registry(),
        reporter=JsonReporter(config.getoption("--apw-reports-dir")),
    )
    config.stash[_RUNTIME_KEY] = rt
    return rt


def build_runner(config):
    from apw.engine.runner import FlowRunner

    rt = get_runtime(config)
    return FlowRunner(
        page=rt.driver.page,
        repo=rt.repo,
        pages=rt.pages,
        reporter=rt.reporter,
        prepare=rt.driver.goto_base,
        screenshot_dir=rt.reporter.out_dir,
    )


def pytest_sessionfinish(session, exitstatus):
    rt = session.config.stash.get(_RUNTIME_KEY, None)
    if rt is not None:
        rt.driver.stop()
        rt.reporter.write_summary()


# ---------- fixtures（框架自测与 flow 项共用运行时） ----------


@pytest.fixture(scope="session")
def apw_env(request):
    return get_runtime(request.config).env


@pytest.fixture(scope="session")
def apw_driver(request):
    return get_runtime(request.config).driver


@pytest.fixture(scope="session")
def apw_repo(request):
    return get_runtime(request.config).repo


@pytest.fixture(scope="session")
def apw_pages(request):
    return get_runtime(request.config).pages


@pytest.fixture(scope="session")
def apw_reporter(request):
    return get_runtime(request.config).reporter


@pytest.fixture
def apw_runner(request):
    return build_runner(request.config)


# ---------- 收集与执行 ----------


def pytest_collect_file(file_path, parent):
    flows_root = Path(parent.config.rootpath) / parent.config.getoption(
        "--apw-flows-dir"
    )
    if file_path.suffix.lower() in {".yaml", ".yml"} and file_path.is_relative_to(
        flows_root
    ):
        return ApwFlowFile.from_parent(parent, path=file_path)
    return None


class ApwFlowFile(pytest.File):
    def collect(self):
        from apw.dsl.loader import load_flow

        try:
            spec = load_flow(self.path)
        except Exception as exc:
            raise pytest.CollectError(f"{self.path}: {exc}") from exc
        return [ApwFlowItem.from_parent(self, name=spec.meta.id, spec=spec)]


class ApwFlowError(Exception):
    def __init__(self, result) -> None:
        self.result = result
        super().__init__(f"flow {result.flow_id} 执行失败")


class ApwFlowItem(pytest.Item):
    def __init__(self, *, spec, **kwargs):
        super().__init__(**kwargs)
        self.spec = spec
        self.result = None
        for platform in spec.meta.platforms:
            self.add_marker(platform)

    def runtest(self):
        rt = get_runtime(self.config)
        active = "desktop" if rt.env.driver.mode == "electron" else "web"
        if active not in self.spec.meta.platforms:
            pytest.skip(f"平台不匹配：flow 需要 {self.spec.meta.platforms}，当前 {active}")

        runner = build_runner(self.config)
        self.result = runner.run(self.spec)
        self._attach_allure()
        if self.result.status != "passed":
            raise ApwFlowError(self.result)

    def _attach_allure(self):
        if self.result is None:
            return
        try:
            import allure
        except ImportError:
            return
        allure.attach(
            self.result.model_dump_json(indent=2),
            name=f"{self.result.flow_id}.json",
            attachment_type=allure.attachment_type.JSON,
        )
        for event in self.result.events:
            if event.screenshot and Path(event.screenshot).exists():
                allure.attach.file(
                    event.screenshot,
                    name=Path(event.screenshot).name,
                    attachment_type=allure.attachment_type.PNG,
                )

    def repr_failure(self, excinfo, style=None):
        if isinstance(excinfo.value, ApwFlowError):
            icons = {"passed": "✓", "failed": "✗", "planned": "○", "skipped": "-"}
            lines = [f"flow {self.result.flow_id}「{self.result.name}」失败："]
            for event in self.result.events:
                line = (
                    f"  {icons[event.status]} [{event.index}] {event.kind}"
                    f" {event.detail or event.error} ({event.duration_ms}ms)"
                )
                if event.error:
                    line += f"\n      {event.error}"
                if event.screenshot:
                    line += f"\n      截图: {event.screenshot}"
                lines.append(line)
            return "\n".join(lines)
        return super().repr_failure(excinfo, style=style)

    def reportinfo(self):
        return self.path, 0, f"flow: {self.spec.meta.id} {self.spec.meta.name}"
