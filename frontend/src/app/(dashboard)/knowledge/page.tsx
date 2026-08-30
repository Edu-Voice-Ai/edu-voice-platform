"use client";

import React, { useState } from "react";
import {
  BookOpen,
  FileText,
  Upload,
  Search,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  FileCode,
  Sparkles,
  HelpCircle,
  Clock,
  Layers,
  Filter,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs } from "@/components/ui/tabs";
import { useDataStore } from "@/hooks/useDataStore";
import { KnowledgeCategory, KnowledgeDocument, FAQItem } from "@/types";
import { formatRelativeDate } from "@/lib/utils";

export default function KnowledgeBasePage() {
  const { documents, addDocument, deleteDocument, faqs, addFAQ, deleteFAQ } = useDataStore();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [activeTab, setActiveTab] = useState<"documents" | "faqs">("documents");

  // Upload modal state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [newDocTitle, setNewDocTitle] = useState("");
  const [newDocCategory, setNewDocCategory] = useState<KnowledgeCategory>("courses");

  // FAQ modal state
  const [isFAQModalOpen, setIsFAQModalOpen] = useState(false);
  const [faqQuestion, setFaqQuestion] = useState("");
  const [faqAnswer, setFaqAnswer] = useState("");
  const [faqCategory, setFaqCategory] = useState<KnowledgeCategory>("courses");

  const filteredDocs = documents.filter((doc) => {
    const matchesSearch = doc.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === "all" || doc.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const filteredFAQs = faqs.filter((faq) => {
    const matchesSearch =
      faq.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
      faq.answer.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === "all" || faq.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const handleUploadSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDocTitle) return;
    addDocument({
      name: newDocTitle.endsWith(".pdf") ? newDocTitle : `${newDocTitle}.pdf`,
      size: 2800000,
      category: newDocCategory,
    });
    setNewDocTitle("");
    setIsUploadModalOpen(false);
  };

  const handleFAQSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!faqQuestion || !faqAnswer) return;
    addFAQ({
      question: faqQuestion,
      answer: faqAnswer,
      category: faqCategory,
      verified: true,
    });
    setFaqQuestion("");
    setFaqAnswer("");
    setIsFAQModalOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-indigo-600" />
            Knowledge Base & Institutional RAG
          </h1>
          <p className="text-xs text-muted-foreground">
            Manage official brochures, fee circulars, eligibility criteria, and verified FAQs.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setIsFAQModalOpen(true)}
            className="text-xs font-semibold"
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> Add FAQ
          </Button>

          <Button
            size="sm"
            variant="gradient"
            onClick={() => setIsUploadModalOpen(true)}
            className="text-xs font-bold shadow-md"
          >
            <Upload className="h-3.5 w-3.5 mr-1" /> Upload Document
          </Button>
        </div>
      </div>

      {/* RAG Readiness Overview Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="p-4 bg-indigo-50/50 border-indigo-100 shadow-sm flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground font-semibold">Indexed Documents</p>
            <p className="text-lg font-bold text-slate-900">{documents.length} Files (96 Chunks)</p>
          </div>
        </Card>

        <Card className="p-4 bg-emerald-50/50 border-emerald-100 shadow-sm flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm">
            <HelpCircle className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground font-semibold">Verified FAQ Pairs</p>
            <p className="text-lg font-bold text-slate-900">{faqs.length} FAQs Grounded</p>
          </div>
        </Card>

        <Card className="p-4 bg-slate-50 border-slate-200 shadow-sm flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-800 text-white shadow-sm">
            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-xs text-muted-foreground font-semibold">RAG Accuracy Status</p>
            <p className="text-lg font-bold text-emerald-700">Zero-Hallucination Safe</p>
          </div>
        </Card>
      </div>

      {/* Main Content Area */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3 border-b border-slate-100 dark:border-slate-800 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setActiveTab("documents")}
                className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                  activeTab === "documents"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                Documents ({documents.length})
              </button>
              <button
                onClick={() => setActiveTab("faqs")}
                className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                  activeTab === "faqs"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                Verified FAQs ({faqs.length})
              </button>
            </div>

            {/* Search & Category Filter */}
            <div className="flex items-center gap-3">
              <div className="w-64">
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search prospectus or FAQs..."
                  leftIcon={<Search className="h-3.5 w-3.5" />}
                  className="h-9 text-xs"
                />
              </div>

              <div className="w-40">
                <Select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  className="h-9 text-xs"
                >
                  <option value="all">All Categories</option>
                  <option value="courses">Courses</option>
                  <option value="fees">Fees & Scholarships</option>
                  <option value="eligibility">Eligibility</option>
                  <option value="hostel">Hostel & Facilities</option>
                  <option value="admission_dates">Dates & Timings</option>
                </Select>
              </div>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-6">
          {activeTab === "documents" ? (
            <div className="space-y-3">
              {filteredDocs.length === 0 ? (
                <div className="text-center py-12 text-xs text-muted-foreground">
                  No documents found matching your search.
                </div>
              ) : (
                filteredDocs.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 hover:border-indigo-200 transition-all"
                  >
                    <div className="flex items-center gap-3.5">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                        <FileText className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-bold text-slate-900">{doc.title}</p>
                          <Badge variant="indigo" className="text-[9px] uppercase">
                            {doc.category}
                          </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          {(doc.fileSizeBytes / 1024 / 1024).toFixed(1)} MB • {doc.chunkCount} Chunks Indexed • Uploaded {formatRelativeDate(doc.uploadedAt)}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <Badge
                        variant={doc.status === "indexed" ? "success" : "warning"}
                        className="text-[10px]"
                      >
                        {doc.status === "indexed" ? "Indexed & Active" : "Vectorizing..."}
                      </Badge>
                      <button
                        onClick={() => deleteDocument(doc.id)}
                        className="p-1.5 text-slate-400 hover:text-red-600 transition-colors"
                        title="Delete Document"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredFAQs.length === 0 ? (
                <div className="text-center py-12 text-xs text-muted-foreground">
                  No FAQs found matching your search.
                </div>
              ) : (
                filteredFAQs.map((faq) => (
                  <div
                    key={faq.id}
                    className="rounded-xl border border-slate-200 bg-white p-4 space-y-2 hover:border-indigo-200 transition-all"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-xs text-indigo-700">Q:</span>
                        <p className="text-xs font-bold text-slate-900">{faq.question}</p>
                        <Badge variant="indigo" className="text-[9px] uppercase">
                          {faq.category}
                        </Badge>
                      </div>
                      <button
                        onClick={() => deleteFAQ(faq.id)}
                        className="p-1 text-slate-400 hover:text-red-600 transition-colors shrink-0"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <div className="flex items-start gap-2 pl-4 border-l-2 border-indigo-200 text-xs text-slate-700 leading-relaxed">
                      <p>{faq.answer}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upload Document Modal */}
      <Modal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        title="Upload Official Knowledge Document"
        description="Provide a prospectus or fee circular to ground your Admission AI."
      >
        <form onSubmit={handleUploadSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-700">Document Title</label>
            <Input
              value={newDocTitle}
              onChange={(e) => setNewDocTitle(e.target.value)}
              placeholder="e.g. ABC_College_Admission_Guidelines_2026.pdf"
              required
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Knowledge Category</label>
            <Select
              value={newDocCategory}
              onChange={(e) => setNewDocCategory(e.target.value as KnowledgeCategory)}
            >
              <option value="courses">Courses & Programs</option>
              <option value="fees">Tuition Fees & Scholarships</option>
              <option value="eligibility">Eligibility & Cutoffs</option>
              <option value="admission_dates">Admission Dates & Deadlines</option>
              <option value="hostel">Hostel & Mess Rules</option>
              <option value="campus">Campus Facilities & Bus Routes</option>
            </Select>
          </div>

          <div className="rounded-xl border-2 border-dashed border-slate-200 p-6 text-center text-xs text-slate-500 bg-slate-50">
            <Upload className="h-6 w-6 mx-auto text-indigo-600 mb-1" />
            <p className="font-semibold text-slate-800">Choose file or drag & drop</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">PDF, DOCX, TXT, CSV up to 25MB</p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsUploadModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="gradient" size="sm" className="font-bold">
              Index Document
            </Button>
          </div>
        </form>
      </Modal>

      {/* Add FAQ Modal */}
      <Modal
        isOpen={isFAQModalOpen}
        onClose={() => setIsFAQModalOpen(false)}
        title="Add Verified FAQ Pair"
        description="Directly provide high-frequency admission questions and answers."
      >
        <form onSubmit={handleFAQSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-700">Question</label>
            <Input
              value={faqQuestion}
              onChange={(e) => setFaqQuestion(e.target.value)}
              placeholder="e.g. When is the last date for MBA applications?"
              required
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Verified Answer</label>
            <Textarea
              rows={3}
              value={faqAnswer}
              onChange={(e) => setFaqAnswer(e.target.value)}
              placeholder="Provide exact factual answer..."
              required
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Category</label>
            <Select
              value={faqCategory}
              onChange={(e) => setFaqCategory(e.target.value as KnowledgeCategory)}
            >
              <option value="courses">Courses</option>
              <option value="fees">Fees & Scholarships</option>
              <option value="eligibility">Eligibility</option>
              <option value="admission_dates">Admission Dates</option>
              <option value="hostel">Hostel</option>
            </Select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsFAQModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="gradient" size="sm" className="font-bold">
              Save FAQ
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
