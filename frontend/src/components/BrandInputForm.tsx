"use client";

import { useState } from "react";
import type { BrandInput } from "@/types";

// Nestle preset data for demo
const PRESETS: Record<string, BrandInput> = {
  kitkat: {
    brand_name: "KitKat",
    product_category: "Chocolate Confectionery",
    current_tagline: "Have a Break, Have a KitKat",
    current_description:
      "Crispy wafer fingers covered in smooth milk chocolate. The perfect companion for your break time — snap, share, and enjoy.",
    target_audience:
      "Young adults and working professionals aged 18-35 seeking a quick, enjoyable break",
  },
  nescafe: {
    brand_name: "Nescafe",
    product_category: "Instant Coffee",
    current_tagline: "It all starts with a Nescafe",
    current_description:
      "Premium instant coffee crafted from responsibly sourced beans. Rich aroma, bold flavor, ready in seconds — fueling moments that matter.",
    target_audience:
      "Coffee lovers aged 25-50 who want quality and convenience",
  },
  maggi: {
    brand_name: "Maggi",
    product_category: "Instant Noodles",
    current_tagline: "2-Minute Noodles",
    current_description:
      "Quick, tasty noodles ready in just 2 minutes. A trusted family favorite with flavors that bring everyone to the table.",
    target_audience:
      "Families and young adults looking for quick, tasty meal solutions",
  },
};

interface Props {
  onSubmit: (input: BrandInput) => void;
  isLoading: boolean;
}

export default function BrandInputForm({ onSubmit, isLoading }: Props) {
  const [form, setForm] = useState<BrandInput>(PRESETS.kitkat);

  const handlePreset = (key: string) => {
    setForm(PRESETS[key]);
  };

  return (
    <div className="glass-card p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold">Brand Analysis Input</h2>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Enter your brand details or select a Nestle demo preset
          </p>
        </div>
      </div>

      {/* Preset buttons */}
      <div className="flex gap-3 mb-6">
        {Object.entries(PRESETS).map(([key, preset]) => (
          <button
            key={key}
            onClick={() => handlePreset(key)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              form.brand_name === preset.brand_name
                ? "bg-[var(--accent)] text-white shadow-lg shadow-[var(--accent)]/25"
                : "bg-[var(--card-border)] text-[var(--text-muted)] hover:bg-[var(--accent)]/20 hover:text-white"
            }`}
          >
            {preset.brand_name}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">
            Brand Name
          </label>
          <input
            value={form.brand_name}
            onChange={(e) => setForm({ ...form, brand_name: e.target.value })}
            className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">
            Product Category
          </label>
          <input
            value={form.product_category}
            onChange={(e) =>
              setForm({ ...form, product_category: e.target.value })
            }
            className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
        </div>
        <div className="col-span-2">
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">
            Current Tagline
          </label>
          <input
            value={form.current_tagline}
            onChange={(e) =>
              setForm({ ...form, current_tagline: e.target.value })
            }
            className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors font-medium"
          />
        </div>
        <div className="col-span-2">
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">
            Product Description
          </label>
          <textarea
            value={form.current_description}
            onChange={(e) =>
              setForm({ ...form, current_description: e.target.value })
            }
            rows={2}
            className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors resize-none"
          />
        </div>
        <div className="col-span-2">
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">
            Target Audience
          </label>
          <input
            value={form.target_audience}
            onChange={(e) =>
              setForm({ ...form, target_audience: e.target.value })
            }
            className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
        </div>
      </div>

      <button
        onClick={() => onSubmit(form)}
        disabled={isLoading || !form.brand_name || !form.current_tagline}
        className="mt-6 w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-red-600 to-red-500 hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
                fill="none"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Running 6-Agent Pipeline...
          </>
        ) : (
          <>Launch Competitive Benchmark</>
        )}
      </button>
    </div>
  );
}
