import FormField from "../components/FormField"
import Footer from "../components/Footer"
import Navbar from "../components/Navbar"
import QuestionCard from "../components/QuestionCard"
import SectionCard from "../components/SectionCard"
import ToggleSwitch from "../components/ToggleSwitch"

const questionData = [
  {
    prompt:
      "A 65-year-old male presents with sudden onset of severe, tearing chest pain radiating to his back. On examination, he is diaphoretic and his blood pressure is significantly different between his left and right arms. What is the most likely diagnosis?",
    options: [
      { key: "A", text: "Acute myocardial infarction" },
      { key: "B", text: "Pulmonary embolism" },
      { key: "C", text: "Aortic dissection" },
      { key: "D", text: "Pericarditis" },
    ],
    selectedKey: "C",
    evidence: {
      label: "Source Evidence / RAG Context",
      source:
        "Aortic dissection presents with severe, tearing chest pain radiating to the back, often with pulse or blood pressure deficits between limbs. [InternalMed_Harrison_3081]",
    },
  },
  {
    prompt:
      "Which of the following classes of antiarrhythmic drugs primarily blocks sodium channels?",
    options: [
      { key: "A", text: "Beta-blockers" },
      { key: "B", text: "Calcium channel blockers" },
      { key: "C", text: "Class I antiarrhythmics" },
      { key: "D", text: "Potassium channel blockers" },
    ],
    selectedKey: "C",
    evidence: {
      label: "Source Evidence / RAG Context",
      source:
        "Class I antiarrhythmic drugs, such as lidocaine and flecainide, primarily exert their effects by blocking cardiac sodium channels. [Pharmacology_Katzung_120]",
    },
  },
  {
    prompt:
      "A patient with chronic kidney disease is found to have elevated serum phosphate levels. Which of the following interventions is most appropriate?",
    options: [
      { key: "A", text: "Increase dietary calcium intake" },
      { key: "B", text: "Administer loop diuretics" },
      { key: "C", text: "Prescribe phosphate binders" },
      { key: "D", text: "Initiate high-dose vitamin D supplementation" },
    ],
    selectedKey: "C",
    evidence: {
      label: "Source Evidence / RAG Context",
      source:
        "Phosphate binders are commonly used in patients with chronic kidney disease to reduce intestinal absorption of phosphate and manage hyperphosphatemia. [Nephrology_Brenner_510]",
    },
  },
]

export default function HomePage() {
  return (
    <div className='app-shell'>
      <Navbar />
      <main className='page-body'>
        <div className='container'>
          <div className='content-grid'>
            <SectionCard title='Exam Configuration'>
              <div className='config-card'>
                <FormField label='Topic'>
                  <input className='text-input' defaultValue='Cardiology' />
                </FormField>
                <FormField label='Competency'>
                  <select className='text-input' defaultValue='Diagnosis'>
                    <option>Diagnosis</option>
                    <option>Therapy</option>
                    <option>Prognosis</option>
                  </select>
                </FormField>
                <FormField label='Question Count'>
                  <input
                    className='text-input'
                    type='number'
                    defaultValue='5'
                  />
                </FormField>
              </div>

              <button type='button' className='ghost-button'>
                + Add Another Topic
              </button>

              <button type='button' className='primary-button'>
                Generate Questions
              </button>
            </SectionCard>

            <SectionCard
              title='Generated Questions'
              action={
                <ToggleSwitch label='Show correct answers' defaultChecked />
              }
            >
              <div className='question-list'>
                {questionData.map((question, index) => (
                  <QuestionCard
                    key={question.prompt.slice(0, 16)}
                    index={index + 1}
                    prompt={question.prompt}
                    options={question.options}
                    selectedKey={question.selectedKey}
                    evidence={question.evidence}
                  />
                ))}
              </div>
            </SectionCard>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  )
}
