"use client";

import { useId, useState } from "react";
import { getGradeLevels, gradeLevelsByProgramme, programmes, subjects } from "@/lib/booking-grade-levels.mjs";
import { CUSTOM_CHOICE, getCurriculumTopics, isSchoolProgramme } from "@/lib/school-curriculum.mjs";

type Props = {
  initialProgramme?: string;
  initialSubject?: string;
  initialLevel?: string;
  initialTopic?: string;
  offeredLevels?: string[];
  includeTopic?: boolean;
};

export function CurriculumFields({ initialProgramme = "", initialSubject = "", initialLevel = "", initialTopic = "", offeredLevels = [], includeTopic = true }: Props) {
  const id = useId();
  const [programme, setProgramme] = useState(initialProgramme);
  const [subject, setSubject] = useState(initialSubject);
  const initialLevels = getGradeLevels(initialProgramme, offeredLevels, initialSubject);
  const [level, setLevel] = useState(initialLevel && !initialLevels.includes(initialLevel) && !isSchoolProgramme(initialProgramme) ? CUSTOM_CHOICE : initialLevel);
  const [customLevel, setCustomLevel] = useState(initialLevel);
  const initialChapters = getCurriculumTopics(initialProgramme, initialSubject, initialLevel).flatMap(group => group.chapters);
  const [topic, setTopic] = useState(initialTopic && initialTopic !== "Full grade syllabus and exam revision" && !initialChapters.includes(initialTopic) ? CUSTOM_CHOICE : initialTopic);
  const [customTopic, setCustomTopic] = useState(initialTopic);
  const currentLevel = level === CUSTOM_CHOICE ? customLevel : level;
  const levels = getGradeLevels(programme, programme === initialProgramme && subject === initialSubject ? offeredLevels : [], subject);
  const groups = getCurriculumTopics(programme, subject, currentLevel);
  const inputClass = "min-h-12 w-full min-w-0 rounded-xl border border-[#c9d5e5] bg-white px-4 font-normal";
  function clearTopic() { setTopic(""); setCustomTopic(""); }
  function clearLevel() { setLevel(""); setCustomLevel(""); clearTopic(); }

  return <>
    <label className="grid min-w-0 gap-2 text-sm font-semibold">Programme
      <select name="programme" required value={programme} onChange={event => { setProgramme(event.target.value); clearLevel(); }} className={inputClass}>
        <option value="">Choose programme</option>
        {programmes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
    <label className="grid min-w-0 gap-2 text-sm font-semibold">Subject
      <select name="subject" required value={subject} onChange={event => { setSubject(event.target.value); clearLevel(); }} className={inputClass}>
        <option value="">Choose subject</option>
        {subjects.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
    <label className="grid min-w-0 gap-2 text-sm font-semibold">Grade / level
      <select name="level" aria-label="Grade / level" required value={level} onChange={event => { setLevel(event.target.value); clearTopic(); }} aria-describedby={`${id}-level-help`} className={inputClass}>
        <option value="">Choose grade / level</option>
        {programme ? levels.map(item => <option key={item} value={item}>{item}</option>) : Object.entries(gradeLevelsByProgramme).map(([key, items]) => <optgroup key={key} label={programmes.find(([value]) => value === key)?.[1] ?? key}>{items.map(item => <option key={item} value={item}>{item}</option>)}</optgroup>)}
        {!isSchoolProgramme(programme) && <option value={CUSTOM_CHOICE}>Other academic level or module</option>}
      </select>
      <span id={`${id}-level-help`} className="text-xs font-normal leading-5 text-[#60708a]">CAPS and IEB Mathematics: Grades 7–12. Mathematical Literacy: Grades 10–12.</span>
    </label>
    {level === CUSTOM_CHOICE && <label className="grid min-w-0 gap-2 text-sm font-semibold">Academic level or module
      <input name="customLevel" required minLength={1} maxLength={80} value={customLevel} onChange={event => { setCustomLevel(event.target.value); clearTopic(); }} className={inputClass} />
    </label>}
    {level !== CUSTOM_CHOICE && !isSchoolProgramme(programme) && <noscript><label>Other academic level or module<input name="customLevel" maxLength={80} className={inputClass} /></label></noscript>}
    {includeTopic && <label className="grid min-w-0 gap-2 text-sm font-semibold">Topic / chapter
      <select name="topic" required value={topic} onChange={event => { setTopic(event.target.value); setCustomTopic(""); }} className={inputClass}>
        <option value="">Choose topic / chapter</option>
        {groups.map(group => <optgroup key={group.title} label={group.title}>{group.chapters.map(chapter => <option key={chapter} value={chapter}>{chapter}</option>)}</optgroup>)}
        {groups.length > 0 && <option value="Full grade syllabus and exam revision">Full grade syllabus and exam revision</option>}
        <option value={CUSTOM_CHOICE}>Another chapter / assignment / exam question</option>
      </select>
    </label>}
    {includeTopic && topic === CUSTOM_CHOICE && <label className="grid min-w-0 gap-2 text-sm font-semibold sm:col-span-2">Your topic, chapter or question
      <input name="customTopic" required minLength={2} maxLength={180} value={customTopic} onChange={event => setCustomTopic(event.target.value)} placeholder="Enter your school chapter, assignment or past-paper question" className={inputClass} />
    </label>}
    {includeTopic && topic !== CUSTOM_CHOICE && <noscript><label>Your topic, chapter or question<input name="customTopic" maxLength={180} className={inputClass} /></label></noscript>}
    {groups.length > 0 && <details className="min-w-0 rounded-xl border border-[#dce4ef] bg-[#f7f9fc] p-4 sm:col-span-2">
      <summary className="cursor-pointer text-sm font-semibold">View {programme.toUpperCase()} {currentLevel} {subjects.find(([value]) => value === subject)?.[1]} syllabus guide</summary>
      <p className="mt-3 text-xs leading-6 text-[#60708a]">CAPS-aligned chapter guide. Chapter names and order vary by school and textbook.{programme === "ieb" && " For IEB support, include your school's chapter or assessment instructions when needed."}{!includeTopic && " Students choose their topic when booking your availability."}</p>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">{groups.map(group => <div key={group.title}><p className="text-sm font-semibold">{group.title}</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-[#60708a]">{group.chapters.map(chapter => <li key={chapter}>{chapter}</li>)}</ul></div>)}</div>
    </details>}
  </>;
}
