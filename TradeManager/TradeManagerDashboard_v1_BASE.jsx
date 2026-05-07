import React, { useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertTriangle, Activity, Shield, Power, RefreshCw, TrendingUp, TrendingDown, PauseCircle, PlayCircle, XCircle, BellRing, MoveVertical } from "lucide-react";
import { motion } from "framer-motion";

const initialTrades = [
  {
    id: "T-8A31F2D1",
    symbol: "NQ",
    direction: "long",
    entry: 18840.25,
    stop: 18828.25,
    tp1: 18852.25,
    tpFinal: null,
    beTrigger: 18846.25,
    last: 18844.00,
    status: "active",
    stopState: "original",
    movedToBE: false,
    tp1Hit: false,
    remainingSize: 2,
    positionSize: 2,
    pnlTicks: 15,
    openedAt: "06:34:22",
    qaHealth: "good",
  },
  {
    id: "T-4F9911A7",
    symbol: "ES",
    direction: "short",
    entry: 5412.5,
    stop: 5418.5,
    tp1: 5406.5,
    tpFinal: null,
    beTrigger: 5409.5,
    last: 5410.25,
    status: "partial",
    stopState: "break_even",
    movedToBE: true,
    tp1Hit: true,
    remainingSize: 1,
    positionSize: 2,
    pnlTicks: 9,
    openedAt: "06:47:05",
    qaHealth: "watch",
  },
];

const riskDefaults = {
  killSwitchActive: false,
  tradingHalted: false,
  drawdownPct: 3.2,
  killSwitchLevel: 11.0,
  dailyTrades: 1,
  maxDailyTrades: 2,
  dailyLosses: 0,
  maxDailyLosses: 1,
  executionFailures: 0,
  qaCritical: 0,
};

// SYMBOL MODEL (continuous vs broker mapping)
const symbolMap = {
  NQ: { chart: "NQ1!", broker: "NQ_FRONT" },
  MNQ: { chart: "MNQ1!", broker: "MNQ_FRONT" },
  ES: { chart: "ES1!", broker: "ES_FRONT" },
  MES: { chart: "MES1!", broker: "MES_FRONT" },
  RTY: { chart: "RTY1!", broker: "RTY_FRONT" },
  M2K: { chart: "MRTY1!", broker: "MRTY_FRONT" },
  RTY: { chart: "RTY1!", broker: "RTY_FRONT" },
  M2K: { chart: "M2K1!", broker: "M2K_FRONT" },
  GC: { chart: "GC1!", broker: "GC_FRONT" },
  MGC: { chart: "MGC1!", broker: "MGC_FRONT" },
};

const tickValueMap = {
  NQ: 5,
  MNQ: 0.5,
  ES: 12.5,
  MES: 1.25,
  RTY: 5,
  M2K: 0.5,
  RTY: 5,
  M2K: 0.5,
  GC: 10,
  MGC: 1,
};

const atrFeed = {
  // Index futures
  NQ: { atr1m: 6.25, last: 18844.0 },
  MNQ: { atr1m: 6.25, last: 18844.0 },
  ES: { atr1m: 2.0, last: 5410.25 },
  MES: { atr1m: 2.0, last: 5410.25 },
  RTY: { atr1m: 18.0, last: 39210.0 },
  M2K: { atr1m: 18.0, last: 39210.0 },
  RTY: { atr1m: 1.8, last: 2287.6 },
  M2K: { atr1m: 0.9, last: 2288.1 },

  // Metals
  GC: { atr1m: 3.4, last: 2418.7 },
  MGC: { atr1m: 3.4, last: 2418.7 },
};

const qaFeed = [
  { time: "06:29:58", level: "CRITICAL", source: "EXECUTION", msg: "Stop placement FAILED" },
  { time: "06:30:01", level: "INFO", source: "SYSTEM", msg: "Heartbeat OK (0.0s)" },
  { time: "06:34:23", level: "INFO", source: "EXECUTION", msg: "submit_stop acknowledged" },
  { time: "06:41:10", level: "WARNING", source: "TRADE_INTEGRITY", msg: "BE flag set but stop not at entry" },
  { time: "06:41:11", level: "INFO", source: "EXECUTION", msg: "submit_stop replacement acknowledged" },
  { time: "06:47:40", level: "INFO", source: "RISK", msg: "Daily trade limit still available" },
];

function statusTone(status) {
  if (status === "active") return "bg-emerald-500/15 text-emerald-700 border-emerald-300";
  if (status === "partial") return "bg-amber-500/15 text-amber-700 border-amber-300";
  if (status === "closed") return "bg-slate-500/15 text-slate-700 border-slate-300";
  return "bg-rose-500/15 text-rose-700 border-rose-300";
}

function qaTone(level) {
  if (level === "CRITICAL") return "text-rose-600 font-semibold";
  if (level === "WARNING") return "text-amber-600";
  return "text-slate-700";
}

function qaBg(level) {
  if (level === "CRITICAL") return "bg-rose-50 border-rose-300 animate-pulse";
  if (level === "WARNING") return "bg-amber-50 border-amber-300";
  return "bg-white border-slate-200";
}

function MetricCard({ title, value, subtitle, icon: Icon, warning = false }) {
  return (
    <Card className="rounded-2xl shadow-sm border-slate-200">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500">{title}</div>
            <div className={`mt-2 text-2xl font-semibold ${warning ? "text-amber-600" : "text-slate-900"}`}>{value}</div>
            <div className="mt-1 text-xs text-slate-500">{subtitle}</div>
          </div>
          <div className={`rounded-2xl p-2 ${warning ? "bg-amber-100" : "bg-slate-100"}`}>
            <Icon className={`h-5 w-5 ${warning ? "text-amber-700" : "text-slate-700"}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function computeRStructure(trade) {
  const initialRisk = Math.abs((trade.entry ?? 0) - (trade.stop ?? 0));
  if (!initialRisk) {
    return {
      initialRisk: 0,
      priceRMove: 0,
      lockedR: 0,
      runnerOpenR: 0,
      runnerContributionR: 0,
      totalCurrentR: 0,
    };
  }

  const directionSign = trade.direction === "short" ? -1 : 1;
  const priceRMove = Number((((trade.last - trade.entry) * directionSign) / initialRisk).toFixed(2));
  const remainingFraction = trade.positionSize ? trade.remainingSize / trade.positionSize : 0;
  const lockedR = trade.tp1Hit ? 0.5 : 0;
  const runnerOpenR = trade.tp1Hit && trade.remainingSize > 0 ? priceRMove : 0;
  const runnerContributionR = trade.tp1Hit && trade.remainingSize > 0
    ? Number((runnerOpenR * remainingFraction).toFixed(2))
    : 0;

  const totalCurrentR = trade.tp1Hit
    ? Number((lockedR + runnerContributionR).toFixed(2))
    : Number((priceRMove * remainingFraction).toFixed(2));

  return {
    initialRisk: Number(initialRisk.toFixed(2)),
    priceRMove,
    lockedR,
    runnerOpenR: Number(runnerOpenR.toFixed(2)),
    runnerContributionR,
    totalCurrentR,
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function TradeVisualPanel({ trade, onUpdateLevels, chartSymbol, brokerSymbol }) {
  const panelRef = useRef(null);
  const [dragKey, setDragKey] = useState(null);
  const dragStartRef = useRef(null);
  const [pendingChange, setPendingChange] = useState(null);
  const [pendingY, setPendingY] = useState(null);
  const [placingTp, setPlacingTp] = useState(false);
  const [localLevels, setLocalLevels] = useState({
    stop: trade.stop,
    entry: trade.entry,
    beTrigger: trade.beTrigger,
    tp1: trade.tp1,
    tpFinal: trade.tpFinal ?? null,
    last: trade.last,
  });

  React.useEffect(() => {
    setLocalLevels({
      stop: trade.stop,
      entry: trade.entry,
      beTrigger: trade.beTrigger,
      tp1: trade.tp1,
      tpFinal: trade.tpFinal,
      last: trade.last,
    });
    setPendingChange(null);
    setPendingY(null);
  }, [trade.id, trade.stop, trade.entry, trade.beTrigger, trade.tp1, trade.tpFinal, trade.last]);

  const levels = useMemo(() => {
    const raw = {
      stop: localLevels.stop,
      entry: localLevels.entry,
      beTrigger: localLevels.beTrigger,
      tp1: localLevels.tp1,
      tpFinal: localLevels.tpFinal ?? null,
      last: localLevels.last,
    };

    const values = Object.values(raw).filter((value) => typeof value === "number" && Number.isFinite(value));
    const min = Math.min(...values) - 6;
    const max = Math.max(...values) + 6;
    const range = max - min || 1;

    const yFor = (price) => {
      const pct = (max - price) / range;
      return clamp(pct * 100, 4, 96);
    };

    return { raw, min, max, range, yFor };
  }, [localLevels]);

  const lineDefs = [
    {
      key: "tp1",
      label: trade.tp1Hit ? "TP1 HIT" : "TP1",
      value: localLevels.tp1,
      tone: trade.tp1Hit
        ? "bg-slate-400 border-slate-500 text-white"
        : "bg-emerald-500 border-emerald-600 text-white",
      locked: trade.tp1Hit,
      hit: trade.tp1Hit,
    },
    ...(localLevels.tpFinal ? [{ key: "tpFinal", label: "TP EXIT", value: localLevels.tpFinal, tone: "bg-yellow-400 border-yellow-500 text-slate-900" }] : []),
    { key: "beTrigger", label: "BE", value: localLevels.beTrigger, tone: "bg-violet-500 border-violet-600 text-white" },
    { key: "entry", label: "ENTRY", value: localLevels.entry, tone: "bg-sky-500 border-sky-600 text-white", locked: true },
    { key: "last", label: "LAST", value: localLevels.last, tone: "bg-slate-700 border-slate-800 text-white", locked: true },
    { key: "stop", label: "STOP", value: localLevels.stop, tone: "bg-rose-500 border-rose-600 text-white" },
  ];

  const handlePointerMove = (event) => {
    if (!dragKey || !panelRef.current) return;
    const rect = panelRef.current.getBoundingClientRect();
    const y = clamp(event.clientY - rect.top, 0, rect.height);
    const ratio = y / rect.height;
    const nextPrice = Number((levels.max - ratio * levels.range).toFixed(2));
    setLocalLevels((prev) => ({ ...prev, [dragKey]: nextPrice }));
  };

  const getPriceFromEvent = (event) => {
    if (!panelRef.current) return null;
    const rect = panelRef.current.getBoundingClientRect();
    const y = clamp(event.clientY - rect.top, 0, rect.height);
    const ratio = y / rect.height;
    return Number((levels.max - ratio * levels.range).toFixed(2));
  };

  const handlePanelClick = (event) => {
    if (!placingTp || dragKey) return;
    const clickedPrice = getPriceFromEvent(event);
    if (clickedPrice == null) return;
    setLocalLevels((prev) => ({ ...prev, tpFinal: clickedPrice }));
    setPendingY(levels.yFor(clickedPrice));
    setPendingChange({ key: "tpFinal", original: localLevels.tpFinal, next: clickedPrice });
    setPlacingTp(false);
  };

  const stopDrag = (_e, isCancel = false) => {
    if (!dragKey) return;

    const original = dragStartRef.current;
    const currentValue = localLevels[dragKey];

    if (isCancel) {
      setLocalLevels((prev) => ({ ...prev, [dragKey]: original }));
      dragStartRef.current = null;
      setDragKey(null);
      return;
    }

    if (original != null && currentValue !== original) {
      const y = levels.yFor(currentValue);
      setPendingY(y);
      setPendingChange({ key: dragKey, original, next: currentValue });
    }

    dragStartRef.current = null;
    setDragKey(null);
  };

  const applyPendingChange = () => {
    if (pendingChange) {
      onUpdateLevels(pendingChange.key, pendingChange.next);
    }
    setPendingChange(null);
    setPendingY(null);
  };

  const cancelPendingChange = () => {
    if (pendingChange) {
      setLocalLevels((prev) => ({ ...prev, [pendingChange.key]: pendingChange.original }));
    }
    setPendingChange(null);
    setPendingY(null);
    setPlacingTp(false);
  };

  const bubbleTop = pendingY == null ? 50 : clamp(pendingY - 8, 8, 88);

  return (
    <Card className="rounded-3xl shadow-sm border-slate-200 overflow-hidden">
      <CardHeader className="shrink-0">
        <CardTitle className="flex items-center gap-2">
          <MoveVertical className="h-5 w-5" />
          Live Trade Visual
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between text-sm text-slate-600">
          <div>{trade.symbol} â€¢ {trade.direction} â€¢ {trade.status}</div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={placingTp ? "default" : "outline"}
              className={`rounded-xl ${placingTp ? "bg-yellow-400 text-slate-900 hover:bg-yellow-500 border-yellow-500" : "border-yellow-400 text-yellow-600 hover:bg-yellow-50"}`}
              onClick={() => setPlacingTp((prev) => !prev)}
            >
              {placingTp ? "Click chart to place TP Exit" : "+ Add TP Exit"}
            </Button>
            <div>{placingTp ? "Click anywhere in chart to place TP Exit" : "Drag stop, TP1, TP Exit, and BE lines"}</div>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-3 text-sm">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <div className="text-slate-500 text-xs">Chart Symbol</div>
            <div className="font-medium mt-1">{chartSymbol}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <div className="text-slate-500 text-xs">Execution Symbol</div>
            <div className="font-medium mt-1">{brokerSymbol}</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <div className="text-slate-500 text-xs">Visual Anchor</div>
            <div className="font-medium mt-1">Centered on live structure for {chartSymbol}</div>
          </div>
        </div>

        <div
          ref={panelRef}
          onClick={handlePanelClick}
          onPointerMove={handlePointerMove}
          onPointerUp={(e) => stopDrag(e, false)}
          onPointerLeave={() => stopDrag(null, true)}
          onPointerCancel={() => stopDrag(null, true)}
          className={`relative h-[480px] rounded-3xl border overflow-hidden select-none ${placingTp ? "border-blue-400 bg-blue-50/30" : "border-slate-200 bg-gradient-to-b from-slate-100 to-white"}`}
          style={{ touchAction: dragKey ? "none" : "pan-y" }}
        >
          {placingTp && !pendingChange ? (
            <div className="absolute left-1/2 top-4 -translate-x-1/2 z-30 rounded-2xl border border-blue-300 bg-blue-50 px-4 py-2 text-xs shadow-md text-blue-900">
              Click on the chart where you want the TP Exit.
            </div>
          ) : null}

          {pendingChange ? (
            <div
              className="absolute left-1/2 -translate-x-1/2 z-30 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-2 text-xs shadow-md"
              style={{ top: `${bubbleTop}%` }}
            >
              <div className="flex items-center gap-3">
                <div className="text-amber-900">
                  {pendingChange.key}: {pendingChange.original == null ? "â€”" : pendingChange.original.toFixed(2)} â†’ {pendingChange.next.toFixed(2)}
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" className="rounded-xl px-2 py-1" onClick={cancelPendingChange}>Cancel</Button>
                  <Button size="sm" className="rounded-xl bg-blue-600 text-white hover:bg-blue-700 px-2 py-1" onClick={applyPendingChange}>Apply</Button>
                </div>
              </div>
            </div>
          ) : null}

          <div className="absolute inset-0 opacity-40">
            {Array.from({ length: 10 }).map((_, i) => (
              <div
                key={i}
                className="absolute left-0 right-0 border-t border-dashed border-slate-300"
                style={{ top: `${(i + 1) * 10}%` }}
              />
            ))}
          </div>

          <div className="absolute right-0 top-0 bottom-0 w-20 bg-white/80 border-l border-slate-200">
            {Array.from({ length: 10 }).map((_, i) => {
              const pct = (i + 1) * 0.1;
              const price = (levels.max - pct * levels.range).toFixed(2);
              return (
                <div
                  key={i}
                  className="absolute right-2 text-xs text-slate-600"
                  style={{ top: `${(i + 1) * 10}%`, transform: "translateY(-50%)" }}
                >
                  {price}
                </div>
              );
            })}
          </div>

          {lineDefs.map((line) => {
            const y = levels.yFor(line.value);
            return (
              <div key={line.key} className="absolute left-0 right-0" style={{ top: `${y}%` }}>
                <div className={`absolute left-0 right-20 border-t-2 ${line.hit ? "border-dashed border-slate-400 opacity-70" : line.locked ? "border-slate-700" : "border-slate-400"}`} />
                <button
                  type="button"
                  disabled={line.locked}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    if (!line.locked) {
                      setDragKey(line.key);
                      dragStartRef.current = localLevels[line.key];
                    }
                  }}
                  className={`absolute left-4 -translate-y-1/2 rounded-full border px-3 py-1 text-xs font-semibold shadow-sm ${line.tone} ${line.hit ? "opacity-75" : ""} ${line.locked ? "cursor-default" : "cursor-grab active:cursor-grabbing"}`}
                >
                  {line.label} {line.value.toFixed(2)}
                </button>
                <div className="absolute right-24 -translate-y-1/2 rounded-full bg-white/95 border border-slate-200 px-3 py-1 text-xs text-slate-700 shadow-sm">
                  {line.key === "last" ? "Live" : line.key === "entry" ? "" : line.hit ? "Filled" : dragKey === line.key ? "Dragging" : "Adjustable"}
                </div>
              </div>
            );
          })}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
          <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">Entry</div><div className="font-medium mt-1">{localLevels.entry.toFixed(2)}</div></div>
          <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">Stop</div><div className="font-medium mt-1">{localLevels.stop.toFixed(2)}</div></div>
          <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">BE Trigger</div><div className="font-medium mt-1">{localLevels.beTrigger.toFixed(2)}</div></div>
          <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">TP1</div><div className="font-medium mt-1">{localLevels.tp1.toFixed(2)} {trade.tp1Hit ? <span className="text-slate-500">(hit)</span> : null}</div></div>
          {localLevels.tpFinal && (
          <div className="rounded-2xl bg-slate-50 p-3">
            <div className="text-slate-500 text-xs">TP Exit</div>
            <div className="font-medium mt-1">{localLevels.tpFinal.toFixed(2)}</div>
          </div>
        )}
        </div>
      </CardContent>
    </Card>
  );
}

function TradeControlCard({ trade, onSelect, onMoveToBE }) {
  const tickValue = tickValueMap[trade.symbol] ?? 1;
  const pnlDollars = (trade.pnlTicks * tickValue * trade.positionSize).toFixed(2);
  const favorable = trade.direction === "long" ? trade.last >= trade.entry : trade.last <= trade.entry;
  const r = computeRStructure(trade);

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="rounded-3xl shadow-sm border-slate-200 overflow-hidden">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-xl flex items-center gap-2">
                {trade.symbol}
                <Badge variant="outline" className={statusTone(trade.status)}>{trade.status}</Badge>
              </CardTitle>
              <div className="mt-1 text-sm text-slate-500">{trade.id} â€¢ opened {trade.openedAt}</div>
            </div>
            <Badge variant="outline" className={trade.direction === "long" ? "border-emerald-300 text-emerald-700" : "border-rose-300 text-rose-700"}>
              {trade.direction === "long" ? <TrendingUp className="h-3.5 w-3.5 mr-1" /> : <TrendingDown className="h-3.5 w-3.5 mr-1" />}
              {trade.direction}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
              <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">Entry</div><div className="font-medium mt-1">{trade.entry}</div></div>
              <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">Last</div><div className="font-medium mt-1">{trade.last}</div></div>
              <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">Stop</div><div className="font-medium mt-1">{trade.stop}</div></div>
              <div className="rounded-2xl bg-slate-50 p-3"><div className="text-slate-500 text-xs">TP1</div><div className="font-medium mt-1">{trade.tp1}</div></div>
              {trade.tpFinal && (
              <div className="rounded-2xl bg-slate-50 p-3">
                <div className="text-slate-500 text-xs">TP Exit</div>
                <div className="font-medium mt-1">{trade.tpFinal}</div>
              </div>
            )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">BE Trigger</div><div className="font-medium mt-1">{trade.beTrigger}</div></div>
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">Stop State</div><div className="font-medium mt-1">{trade.stopState}</div></div>
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">Contracts Remaining</div><div className="font-medium mt-1">{trade.remainingSize} / {trade.positionSize}</div></div>
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">TP1 Status</div><div className="font-medium mt-1">{trade.tp1Hit ? "Filled" : "Pending"}</div></div>
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">PnL</div><div className={`font-medium mt-1 ${favorable ? "text-emerald-700" : "text-rose-700"}`}>${pnlDollars}</div></div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">Initial Risk</div><div className="font-medium mt-1">{r.initialRisk} pts</div></div>
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">Locked R</div><div className="font-medium mt-1">{r.lockedR.toFixed(2)}R</div></div>
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">Runner R</div><div className="font-medium mt-1">{trade.tp1Hit ? `${r.runnerOpenR.toFixed(2)}R open` : "Not active"}</div></div>
              <div className="rounded-2xl border border-slate-200 p-3"><div className="text-slate-500 text-xs">Total Current R</div><div className="font-medium mt-1">{r.totalCurrentR.toFixed(2)}R</div></div>
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              <Button className="rounded-2xl" onClick={() => onSelect(trade.id)}><Activity className="mr-2 h-4 w-4" />Manage Trade</Button>
              <Button
                variant="outline"
                className="rounded-2xl"
                onClick={() => {
                  onSelect(trade.id);
                  onMoveToBE(trade.id, trade.entry);
                }}
              >
                <Shield className="mr-2 h-4 w-4" />Move Stop to BE
              </Button>
              
              <Button variant="outline" className="rounded-2xl"><PauseCircle className="mr-2 h-4 w-4" />Pause Auto Mgmt</Button>
              <Button variant="destructive" className="rounded-2xl"><XCircle className="mr-2 h-4 w-4" />Flatten</Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export default function TradeManagerDashboardV1() {
  const audioRef = useRef(null);
  const [criticalLock, setCriticalLock] = useState(true);

  const playAlert = () => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      audioRef.current.play().catch(() => {});
    }
  };
  
  const [trades, setTrades] = useState(initialTrades);
  const [risk, setRisk] = useState(riskDefaults);
  const [selectedTradeId, setSelectedTradeId] = useState(initialTrades[0].id);
  const [manualStop, setManualStop] = useState("");
  const [manualTp1, setManualTp1] = useState("");
  const [manualFinalTarget, setManualFinalTarget] = useState("");
  const [entryForm, setEntryForm] = useState({
    symbol: "NQ",
    direction: "long",
    atrMultiple: "1.0",
  });
  const [entryMessage, setEntryMessage] = useState("");
  const [bannerMessage, setBannerMessage] = useState("");
  const workspaceRef = useRef(null);

  // AUTO ALERT ON CRITICAL
  React.useEffect(() => {
    const hasCritical = qaFeed.some(q => q.level === "CRITICAL");
    if (hasCritical) {
      setCriticalLock(true);
      playAlert();
    }
  }, []);

  const selectedTrade = useMemo(
    () => trades.find((t) => t.id === selectedTradeId) ?? trades[0],
    [trades, selectedTradeId]
  );
  const selectedR = computeRStructure(selectedTrade);

  const selectedChartSymbol = symbolMap[selectedTrade.symbol]?.chart ?? `${selectedTrade.symbol}1!`;
  const selectedBrokerSymbol = symbolMap[selectedTrade.symbol]?.broker ?? `${selectedTrade.symbol}_FRONT`;

  const liveAtr = atrFeed[entryForm.symbol]?.atr1m ?? 0;
  const chartSymbol = symbolMap[entryForm.symbol]?.chart;
  const brokerSymbol = symbolMap[entryForm.symbol]?.broker;
  const liveLast = atrFeed[entryForm.symbol]?.last ?? 0;
  const parsedAtrMultiple = Number(entryForm.atrMultiple || 0);

  const computedStopOffset = useMemo(() => {
    if (!liveAtr || !parsedAtrMultiple) return "";
    return (liveAtr * parsedAtrMultiple).toFixed(2);
  }, [liveAtr, parsedAtrMultiple]);

  const updateEntryField = (key, value) => {
    setEntryForm((prev) => ({ ...prev, [key]: value }));
  };

  
  const updateSelectedTradeLevel = (levelKey, value) => {
    setTrades((prev) =>
      prev.map((trade) =>
        trade.id === selectedTradeId
          ? {
              ...trade,
              [levelKey]: value,
            }
          : trade
      )
    );

    if (levelKey === "stop") setManualStop(String(value));
    if (levelKey === "tp1") setManualTp1(String(value));
    if (levelKey === "tpFinal") setManualFinalTarget(String(value));
  };

  const moveTradeToBE = (tradeId, entryPrice) => {
    setTrades((prev) =>
      prev.map((trade) =>
        trade.id === tradeId
          ? {
              ...trade,
              stop: entryPrice,
              stopState: "break_even",
              movedToBE: true,
            }
          : trade
      )
    );

    if (tradeId === selectedTradeId) {
      setManualStop(String(entryPrice));
    }
  };

  const buildStagedTrade = () => {
    const symbol = entryForm.symbol;
    const direction = entryForm.direction;
    const atr = atrFeed[symbol]?.atr1m ?? 0;
    const last = atrFeed[symbol]?.last ?? 0;
    const atrMultiple = Number(entryForm.atrMultiple || 1);
    const stopOffset = atr * atrMultiple;

    if (!symbol || !direction || !atr || !last || !stopOffset) {
      setEntryMessage("Unable to stage trade. Missing live ATR or last price.");
      return;
    }

    const entry = last;
    const stop = direction === "long" ? entry - stopOffset : entry + stopOffset;
    const beTrigger = direction === "long" ? entry + atr : entry - atr;
    const tp1 = direction === "long" ? entry + stopOffset : entry - stopOffset;
    const tpFinal = null;

    const stagedTrade = {
      id: `T-${Math.random().toString(16).slice(2, 10).toUpperCase()}`,
      symbol,
      direction,
      entry: Number(entry.toFixed(2)),
      stop: Number(stop.toFixed(2)),
      tp1: Number(tp1.toFixed(2)),
      tpFinal: null,
      beTrigger: Number(beTrigger.toFixed(2)),
      last: Number(last.toFixed(2)),
      status: "pending",
      stopState: "original",
      movedToBE: false,
      tp1Hit: false,
      remainingSize: 2,
      positionSize: 2,
      pnlTicks: 0,
      openedAt: "STAGED",
      qaHealth: "good",
    };

    setTrades((prev) => [stagedTrade, ...prev]);
    setSelectedTradeId(stagedTrade.id);
    setManualStop(String(stagedTrade.stop));
    setManualTp1(String(stagedTrade.tp1));
    setManualFinalTarget("");
    setRisk((prev) => ({ ...prev, dailyTrades: Math.min(prev.dailyTrades + 1, prev.maxDailyTrades) }));
    setEntryMessage(`Staged ${symbol} ${direction} trade using ${atrMultiple}x ATR stop.`);
  };

  const loadSelectedTradeIntoVisual = () => {
    const latest = trades[0];
    if (!latest) return;
    setSelectedTradeId(latest.id);
    setManualStop(String(latest.stop));
    setManualTp1(String(latest.tp1));
    setManualFinalTarget(latest.tpFinal ? String(latest.tpFinal) : "");
    setEntryMessage(`Loaded ${latest.symbol} ${latest.direction} into visual manager.`);
  };

  const activeAlerts = qaFeed.filter((q) => q.level === "CRITICAL" || q.level === "WARNING");
  const topAlert = activeAlerts[0] ?? null;

  const acknowledgeTopAlert = () => {
    if (!topAlert) return;
    setBannerMessage(`${topAlert.level} alert acknowledged: ${topAlert.source}`);
    if (topAlert.level === "CRITICAL") {
      setCriticalLock(false);
    }
  };

  const focusQaPanel = () => {
    const el = document.getElementById("qa-feed-panel");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      setBannerMessage(`Focused QA feed: ${topAlert?.source ?? "alerts"}`);
    }
  };

  const flattenFocusedTrade = () => {
    setTrades((prev) =>
      prev.map((trade) =>
        trade.id === selectedTradeId
          ? {
              ...trade,
              status: "closed",
              remainingSize: 0,
              pnlTicks: 0,
            }
          : trade
      )
    );
    setBannerMessage(`Flatten assist triggered for ${selectedTrade.symbol}.`);
  };

  const globalShutdown = () => {
    setTrades((prev) =>
      prev.map((trade) => ({
        ...trade,
        status: "closed",
        remainingSize: 0,
        pnlTicks: 0,
      }))
    );

    setRisk((prev) => ({
      ...prev,
      tradingHalted: true,
      killSwitchActive: true,
    }));

    setBannerMessage("GLOBAL SHUTDOWN triggered. All trades flattened and trading halted.");
    setCriticalLock(false);
  };

  const focusWorkspace = () => {
    requestAnimationFrame(() => {
      workspaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    setBannerMessage("Workspace focused. Continue scrolling normally from here.");
  };

  return (
    <>
      <audio ref={audioRef} src="https://actions.google.com/sounds/v1/alarms/alarm_clock.ogg" preload="auto" />

      {/* CRITICAL LOCK OVERLAY */}
      {criticalLock && qaFeed.some(q => q.level === "CRITICAL") && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="bg-white rounded-3xl p-8 max-w-md w-full text-center space-y-4 shadow-2xl">
            <div className="text-2xl font-semibold text-rose-600">CRITICAL SYSTEM ALERT</div>
            <div className="text-slate-700">
              A critical issue has been detected. You must acknowledge before continuing.
            </div>

            <div className="space-y-2">
              {qaFeed.filter(q => q.level === "CRITICAL").map((item, idx) => (
                <div key={idx} className="text-sm text-rose-700 font-medium">
                  {item.source}: {item.msg}
                </div>
              ))}
            </div>

            <div className="flex gap-3 justify-center pt-4">
              <Button
                variant="destructive"
                className="rounded-2xl"
                onClick={() => setCriticalLock(false)}
              >
                ACKNOWLEDGE
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="min-h-screen bg-slate-50 px-2 md:px-3 py-4">
      <div className="max-w-full mx-auto space-y-6 pb-24">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm text-slate-500">Randle System â€¢ Trade Manager</div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Command Dashboard v1</h1>
            <p className="text-sm text-slate-600 mt-1">Monitor live state, approve manual overrides, and intervene fast without touching the backend logic directly.</p>
          </div>
          <div className="hidden" />
        </motion.div>

        <div className="sticky top-0 z-40 space-y-4 bg-slate-50/95 backdrop-blur-sm pb-4">
          {/* TOP ALERT BANNER */}
          {activeAlerts.length > 0 && (
            <div className={`rounded-2xl border p-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between ${topAlert?.level === "CRITICAL" ? "bg-rose-50 border-rose-300" : "bg-amber-50 border-amber-300"}`}>
              <div className="flex items-start gap-3">
                <AlertTriangle className={`${topAlert?.level === "CRITICAL" ? "text-rose-600" : "text-amber-600"} h-5 w-5 mt-0.5`} />
                <div>
                  <div className={`text-sm font-semibold ${topAlert?.level === "CRITICAL" ? "text-rose-700" : "text-amber-700"}`}>
                    {topAlert?.level === "CRITICAL" ? "CRITICAL ISSUE DETECTED" : "WARNING ACTIVE"}
                  </div>
                  <div className="text-sm text-slate-700 mt-1">
                    {topAlert?.source}: {topAlert?.msg}
                  </div>
                  <div className="text-xs text-slate-600 mt-1">
                    {activeAlerts.length} active alert{activeAlerts.length === 1 ? "" : "s"}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="rounded-2xl" onClick={focusQaPanel}>View Alerts</Button>
                <Button variant="outline" className="rounded-2xl" onClick={flattenFocusedTrade}>Flatten Focused Trade</Button>
                <Button variant="destructive" className="rounded-2xl" onClick={globalShutdown}>Shutdown All</Button>
                <Button className="rounded-2xl" onClick={acknowledgeTopAlert}>Acknowledge</Button>
              </div>
            </div>
          )}

          {bannerMessage ? (
            <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
              {bannerMessage}
            </div>
          ) : null}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <MetricCard title="Kill Switch" value={risk.killSwitchActive ? "ACTIVE" : "OFF"} subtitle={`Trips at ${risk.killSwitchLevel}% DD`} icon={Power} warning={risk.killSwitchActive} />
            <MetricCard title="Trading Status" value={risk.tradingHalted ? "HALTED" : "LIVE"} subtitle="System execution permission" icon={risk.tradingHalted ? PauseCircle : PlayCircle} warning={risk.tradingHalted} />
            <MetricCard title="Drawdown" value={`${risk.drawdownPct}%`} subtitle="Current model drawdown" icon={AlertTriangle} warning={risk.drawdownPct >= 8} />
            <MetricCard title="Daily Trades" value={`${risk.dailyTrades}/${risk.maxDailyTrades}`} subtitle="Trade count gate" icon={Activity} warning={risk.dailyTrades >= risk.maxDailyTrades} />
            <MetricCard title="Failure Count" value={`${risk.executionFailures + risk.qaCritical}`} subtitle="Execution + QA critical" icon={Shield} warning={risk.executionFailures + risk.qaCritical > 0} />
          </div>

          <Card className="rounded-3xl shadow-sm border-slate-200">
            <CardContent className="p-4">
              <div className="grid md:grid-cols-2 xl:grid-cols-8 gap-3 text-sm">
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Focused Trade</div>
                  <div className="font-medium mt-1">{selectedTrade.symbol} â€¢ {selectedTrade.direction}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Status</div>
                  <div className="font-medium mt-1">{selectedTrade.status}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Entry</div>
                  <div className="font-medium mt-1">{selectedTrade.entry}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Stop</div>
                  <div className="font-medium mt-1">{selectedTrade.stop}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Last</div>
                  <div className="font-medium mt-1">{selectedTrade.last}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Contracts Remaining</div>
                  <div className="font-medium mt-1">{selectedTrade.remainingSize} / {selectedTrade.positionSize}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">TP1</div>
                  <div className="font-medium mt-1">{selectedTrade.tp1}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">TP Exit</div>
                  <div className="font-medium mt-1">{selectedTrade.tpFinal}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Locked R</div>
                  <div className="font-medium mt-1">{selectedR.lockedR.toFixed(2)}R</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3">
                  <div className="text-slate-500 text-xs">Runner R</div>
                  <div className="font-medium mt-1">{selectedTrade.tp1Hit ? `${selectedR.runnerOpenR.toFixed(2)}R` : "Not active"}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="rounded-3xl shadow-sm border-slate-200 overflow-hidden">
          <CardHeader className="shrink-0">
            <CardTitle>Manual Entry Console</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Symbol</label>
                <select
                  value={entryForm.symbol}
                  onChange={(e) => updateEntryField("symbol", e.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm"
                >
                  <option value="NQ">NQ</option>
                  <option value="MNQ">MNQ</option>
                  <option value="ES">ES</option>
                  <option value="MES">MES</option>
                  <option value="RTY">RTY</option>
                  <option value="M2K">M2K</option>
                  <option value="RTY">RTY</option>
                  <option value="M2K">M2K</option>
                  <option value="GC">GC</option>
                  <option value="MGC">MGC</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Direction</label>
                <select
                  value={entryForm.direction}
                  onChange={(e) => updateEntryField("direction", e.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm"
                >
                  <option value="long">Long</option>
                  <option value="short">Short</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Position Size</label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">2</div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Mode</label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">Manual Test</div>
              </div>
            </div>

            <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Chart Symbol</label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">{chartSymbol}</div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Broker Symbol</label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">{brokerSymbol}</div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">1m ATR (Live Feed)</label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">{liveAtr}</div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">ATR Multiple for Stop</label>
                <Input value={entryForm.atrMultiple} onChange={(e) => updateEntryField("atrMultiple", e.target.value)} placeholder="1.0" className="rounded-2xl" />
                <div className="flex flex-wrap gap-2 pt-2">
                  {["1.0", "1.5", "2.0"].map((preset) => (
                    <Button
                      key={preset}
                      type="button"
                      size="sm"
                      variant={entryForm.atrMultiple === preset ? "default" : "outline"}
                      className="rounded-xl"
                      onClick={() => updateEntryField("atrMultiple", preset)}
                    >
                      {preset}x
                    </Button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Computed Stop Offset</label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">{computedStopOffset || "â€”"}</div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">Last Price</label>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-900">{liveLast}</div>
              </div>
            </div>

            <div className="flex items-center justify-start gap-3">
              <div className="flex items-center gap-2">
                <Button className="rounded-2xl bg-blue-600 text-white hover:bg-blue-700" onClick={buildStagedTrade}>Submit Manual Trade</Button>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
              For phase 1, manual entries still need to route through Trade Manager validation. The broker fill becomes the true entry price, so this panel stays intentionally minimal. For phase 1 you only choose symbol and direction, confirm the fixed test size of 2, and use the live 1-minute ATR to define stop distance. TP1 is the half-off target. TP Exit is the full exit target for the remaining position. BE trigger and all target adjustments belong below in the manager area, not up here.
            </div>

            {entryMessage ? (
              <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-800">
                {entryMessage}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* MAIN LAYOUT â€” NO TABS */}
                <div
          ref={workspaceRef}
          className="grid xl:grid-cols-[1.2fr_.8fr] gap-4"
        >
          {/* LEFT â€” VISUAL TRADE PANEL */}
          <TradeVisualPanel
            trade={selectedTrade}
            onUpdateLevels={updateSelectedTradeLevel}
            chartSymbol={selectedChartSymbol}
            brokerSymbol={selectedBrokerSymbol}
          />

          {/* RIGHT â€” TRADE LIST */}
          <div className="space-y-4">
            {trades.map((trade) => (
              <TradeControlCard key={trade.id} trade={trade} onSelect={setSelectedTradeId} onMoveToBE={moveTradeToBE} />
            ))}
          </div>
        </div>

        

        {/* LOWER SECTION */}
        <div className="grid lg:grid-cols-[1.2fr_.8fr] gap-4">
          {/* MANUAL OVERRIDE */}
          <Card className="rounded-3xl shadow-sm border-slate-200">
            <CardHeader>
              <CardTitle>Selected Trade Override Panel</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-2xl bg-slate-50 p-4 text-sm">
                <div className="font-medium text-slate-900">{selectedTrade.symbol} â€¢ {selectedTrade.id}</div>
                <div className="text-slate-600 mt-1">Direction: {selectedTrade.direction} â€¢ Status: {selectedTrade.status} â€¢ Remaining: {selectedTrade.remainingSize}</div>
              </div>

              <div className="grid md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-700">Manual Stop Price</label>
                  <Input value={manualStop} onChange={(e) => setManualStop(e.target.value)} placeholder="Enter new stop" className="rounded-2xl" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-700">Manual TP1 Price</label>
                  <Input value={manualTp1} onChange={(e) => setManualTp1(e.target.value)} placeholder="Enter TP1" className="rounded-2xl" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-700">Manual TP Exit Price</label>
                  <Input value={manualFinalTarget} onChange={(e) => setManualFinalTarget(e.target.value)} placeholder="Enter final target" className="rounded-2xl" />
                </div>
              </div>

              <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
                <Button className="rounded-2xl">Replace Stop</Button>
                <Button variant="outline" className="rounded-2xl">Replace TP1</Button>
                <Button
                  variant="outline"
                  className="rounded-2xl border-yellow-400 text-yellow-700 hover:bg-yellow-50"
                  onClick={() => {
                    if (!manualFinalTarget) return;
                    updateSelectedTradeLevel("tpFinal", Number(manualFinalTarget));
                  }}
                >
                  Set / Update TP Exit
                </Button>
                <Button
                  variant="outline"
                  className="rounded-2xl"
                  onClick={() => {
                    updateSelectedTradeLevel("stop", selectedTrade.entry);
                  }}
                >
                  Move to Break Even
                </Button>
                <Button variant="outline" className="rounded-2xl">Close Half</Button>
                <Button variant="outline" className="rounded-2xl">Resume Auto Mgmt</Button>
                <Button variant="destructive" className="rounded-2xl">Flatten Now</Button>
              </div>
            </CardContent>
          </Card>

          {/* QA FEED */}
          <Card id="qa-feed-panel" className="rounded-3xl shadow-sm border-slate-200">
            <CardHeader><CardTitle>QA / System Feed</CardTitle></CardHeader>
            <CardContent>
              {/* PINNED ALERTS */}
              <div className="space-y-2 mb-4">
                {qaFeed.filter(q => q.level === "CRITICAL" || q.level === "WARNING").map((item, idx) => (
                  <div key={idx} className={`flex items-start justify-between gap-4 rounded-2xl border p-3 ${qaBg(item.level)}`}>
                    <div>
                      <div className="text-sm font-semibold text-slate-900">{item.source}</div>
                      <div className={`text-sm mt-1 ${qaTone(item.level)}`}>{item.msg}</div>
                    </div>
                    <div className="text-xs text-slate-500 whitespace-nowrap">{item.time} â€¢ {item.level}</div>
                  </div>
                ))}
              </div>

              {/* FULL FEED */}
              <div className="space-y-3 max-h-[300px] overflow-y-auto">
                {qaFeed.map((item, idx) => (
                  <div key={idx} className={`flex items-start justify-between gap-4 rounded-2xl border p-3 ${qaBg(item.level)}`}>
                    <div>
                      <div className="text-sm font-medium text-slate-900">{item.source}</div>
                      <div className={`text-sm mt-1 ${qaTone(item.level)}`}>{item.msg}</div>
                    </div>
                    <div className="text-xs text-slate-500 whitespace-nowrap">{item.time} â€¢ {item.level}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
    </>
  );
}
