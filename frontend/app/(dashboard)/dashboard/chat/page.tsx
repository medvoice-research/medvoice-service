'use client';

import { useState, useRef, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Send, Bot, User, Loader2, BookOpen } from 'lucide-react';

interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    sources?: { content: string; metadata?: Record<string, unknown> }[];
}

export default function ChatPage() {
    const [patientHash, setPatientHash] = useState('');
    const [sessionId, setSessionId] = useState<string | undefined>();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const sendMessage = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !patientHash.trim() || loading) return;

        const userMsg: ChatMessage = { role: 'user', content: input };
        setMessages((prev) => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            const res = await fetch('/api/medvoice/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: input,
                    patient_id_encrypted: patientHash,
                    session_id: sessionId,
                }),
            });

            if (!res.ok) throw new Error(`Chat failed (${res.status})`);
            const data = await res.json();

            if (data.session_id) setSessionId(data.session_id);

            const assistMsg: ChatMessage = {
                role: 'assistant',
                content: data.answer || 'No response received.',
                sources: data.sources,
            };
            setMessages((prev) => [...prev, assistMsg]);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: `Error: ${(err as Error).message}`,
                },
            ]);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="p-4 sm:p-6 border-b">
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                    Medical Assistant
                </h1>
                <p className="text-muted-foreground mt-1 text-sm">
                    AI-powered Q&A about patient records
                </p>

                {/* Patient selector */}
                <div className="mt-4 flex gap-2 max-w-md">
                    <div className="flex-1 space-y-1">
                        <Label htmlFor="patientHash" className="text-xs">
                            Patient Hash
                        </Label>
                        <Input
                            id="patientHash"
                            value={patientHash}
                            onChange={(e) => setPatientHash(e.target.value)}
                            placeholder="e.g. 154c26a1"
                            className="font-mono text-sm"
                        />
                    </div>
                    {sessionId && (
                        <Button
                            variant="outline"
                            size="sm"
                            className="self-end"
                            onClick={() => {
                                setMessages([]);
                                setSessionId(undefined);
                            }}
                        >
                            New Session
                        </Button>
                    )}
                </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
                {messages.length === 0 && (
                    <div className="text-center py-16 text-muted-foreground">
                        <Bot className="w-12 h-12 mx-auto mb-3 opacity-30" />
                        <p className="text-sm font-medium">Ask about a patient&apos;s records</p>
                        <p className="text-xs mt-1">
                            Enter a patient hash above, then ask your question
                        </p>
                    </div>
                )}

                {messages.map((msg, i) => (
                    <div
                        key={i}
                        className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}
                    >
                        {msg.role === 'assistant' && (
                            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                                <Bot className="w-4 h-4 text-primary" />
                            </div>
                        )}

                        <div
                            className={`max-w-[80%] rounded-lg px-4 py-3 text-sm ${msg.role === 'user'
                                ? 'bg-primary text-primary-foreground'
                                : 'bg-muted'
                                }`}
                        >
                            <p className="whitespace-pre-wrap">{msg.content}</p>

                            {/* Sources */}
                            {msg.sources && msg.sources.length > 0 && (
                                <div className="mt-3 pt-3 border-t border-border/50">
                                    <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground mb-2">
                                        <BookOpen className="w-3 h-3" />
                                        Sources
                                    </div>
                                    {msg.sources.map((src, j) => (
                                        <div
                                            key={j}
                                            className="text-xs text-muted-foreground bg-background/50 rounded p-2 mt-1"
                                        >
                                            {src.content.slice(0, 200)}
                                            {src.content.length > 200 && '...'}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {msg.role === 'user' && (
                            <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center shrink-0">
                                <User className="w-4 h-4 text-secondary-foreground" />
                            </div>
                        )}
                    </div>
                ))}

                {loading && (
                    <div className="flex gap-3">
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                            <Bot className="w-4 h-4 text-primary" />
                        </div>
                        <div className="bg-muted rounded-lg px-4 py-3 flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">Thinking...</span>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t">
                <form onSubmit={sendMessage} className="flex gap-2 max-w-3xl mx-auto">
                    <Input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={
                            patientHash
                                ? 'Ask about this patient...'
                                : 'Enter a patient hash first'
                        }
                        disabled={!patientHash.trim() || loading}
                        className="flex-1"
                    />
                    <Button
                        type="submit"
                        disabled={!input.trim() || !patientHash.trim() || loading}
                        aria-label="Send message"
                    >
                        <Send className="w-4 h-4" />
                    </Button>
                </form>
            </div>
        </div>
    );
}
