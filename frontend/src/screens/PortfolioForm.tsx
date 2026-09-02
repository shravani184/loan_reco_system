import { useState } from "react";
import type { AssetType, Holding } from "../types";

const ASSET_TYPES: AssetType[] = [
  "STOCKS",
  "MUTUAL_FUNDS",
  "FIXED_DEPOSIT",
  "BONDS",
  "CASH",
  "CRYPTO",
];

interface Props {
  holdings: Holding[];
  onChange: (holdings: Holding[]) => void;
  onContinue: () => void;
  onSkip: () => void;
  onBack: () => void;
}

function blankHolding(): Holding {
  return { asset_type: "STOCKS", current_value: 0, invested_value: 0 };
}

export default function PortfolioForm({
  holdings,
  onChange,
  onContinue,
  onSkip,
  onBack,
}: Props) {
  const [newHolding, setNewHolding] = useState<Holding>(blankHolding());

  const add = () => {
    if (newHolding.current_value <= 0) return;
    onChange([...holdings, newHolding]);
    setNewHolding(blankHolding());
  };

  const remove = (index: number) => {
    onChange(holdings.filter((_, i) => i !== index));
  };

  const hasInvestments = holdings.length > 0;

  return (
    <section className="card card-pad card-accent">
      <h2 className="section-heading">Your investments (optional)</h2>
      <p className="section-sub">
        Holdings you could liquidate to fund the loan. This lets the system model
        borrow vs liquidate strategies. Skip it if you have no investments.
      </p>

      <div className="mt-4 rounded-lg border border-sky-200 bg-gradient-to-r from-sky-50 to-blue-50 p-3 text-sm">
        <span className="font-semibold text-sky-800">
          Don't have investments?
        </span>{" "}
        <span className="text-sky-700">
          Choose <span className="font-semibold">"Skip — I have no investments"</span>{" "}
          to proceed on a pure-borrow basis.
        </span>
      </div>

      {hasInvestments ? (
        <ul className="mt-4 space-y-2">
          {holdings.map((h, i) => (
            <li
              key={i}
              className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
            >
              <span>
                <span className="font-medium">{h.asset_type.replace(/_/g, " ").toLowerCase()}</span>{" "}
                <span className="text-slate-500">
                  — {h.current_value.toLocaleString("en-IN")}
                </span>
              </span>
              <button
                onClick={() => remove(i)}
                className="text-xs font-medium text-red-600 hover:text-red-800"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-slate-400">No holdings added.</p>
      )}

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div>
          <label className="field-label" htmlFor="holding_asset">Asset</label>
          <select
            id="holding_asset"
            className="field-input"
            value={newHolding.asset_type}
            onChange={(e) =>
              setNewHolding({ ...newHolding, asset_type: e.target.value as AssetType })
            }
          >
            {ASSET_TYPES.map((a) => (
              <option key={a} value={a}>
                {a.replace(/_/g, " ").toLowerCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="hold_current">Current value (₹)</label>
          <input
            id="hold_current"
            className="field-input"
            type="number"
            min={0}
            value={newHolding.current_value || ""}
            onChange={(e) => setNewHolding({ ...newHolding, current_value: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="hold_invested">Invested value (₹)</label>
          <input
            id="hold_invested"
            className="field-input"
            type="number"
            min={0}
            value={newHolding.invested_value || ""}
            onChange={(e) => setNewHolding({ ...newHolding, invested_value: Number(e.target.value) })}
          />
        </div>
        <div className="flex items-end">
          <button className="btn-secondary w-full" onClick={add}>
            Add holding
          </button>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between">
        <button className="btn-secondary" onClick={onBack}>
          Back
        </button>
        <div className="flex gap-3">
          <button className="btn-secondary" onClick={onSkip}>
            Skip — I have no investments
          </button>
          <button className="btn-primary" onClick={onContinue}>
            Continue with holdings
          </button>
        </div>
      </div>
    </section>
  );
}