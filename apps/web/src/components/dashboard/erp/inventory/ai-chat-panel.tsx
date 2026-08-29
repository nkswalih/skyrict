"use client";

import { useState } from "react";
import { Bot, Loader2, Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/http";
import { queryInventory, type NlQueryResponse } from "@/lib/api/ai-api";

export function AiChatPanel() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<NlQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await queryInventory(q);
      setResult(response);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Query failed. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Bot aria-hidden="true" className="size-4" />
        </div>
        <h3 className="font-display text-base font-semibold text-foreground">
          Inventory AI Assistant
        </h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Ask a question about your inventory in plain English.
      </p>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. How many laptop chargers do we have?"
          disabled={loading}
          className="flex-1"
        />
        <Button type="submit" disabled={loading || !question.trim()} size="icon">
          {loading ? (
            <Loader2 aria-hidden="true" className="size-4 animate-spin" />
          ) : (
            <Send aria-hidden="true" className="size-4" />
          )}
        </Button>
      </form>
      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}
      {result && (
        <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-2">
          <p className="text-sm text-foreground whitespace-pre-wrap">{result.answer}</p>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {result.model_used && (
              <Badge variant="outline" className="text-xs">
                {result.model_used}
              </Badge>
            )}
            <span>{result.latency_ms}ms</span>
          </div>
        </div>
      )}
    </div>
  );
}
