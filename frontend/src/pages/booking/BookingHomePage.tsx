import { Link } from 'react-router-dom'
import { Calendar, Scissors, Clock } from 'lucide-react'

export default function BookingHomePage() {
  return (
    <div className="text-center space-y-8">
      <div className="space-y-3">
        <h1 className="text-3xl font-bold text-foreground">New Style Hair</h1>
        <p className="text-muted-foreground text-lg">Prenota il tuo appuntamento online in pochi passi</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-xl mx-auto">
        <div className="card p-4 text-center">
          <Scissors className="w-8 h-8 text-primary mx-auto mb-2" />
          <p className="text-sm font-medium">Scegli il servizio</p>
        </div>
        <div className="card p-4 text-center">
          <Calendar className="w-8 h-8 text-primary mx-auto mb-2" />
          <p className="text-sm font-medium">Seleziona data e ora</p>
        </div>
        <div className="card p-4 text-center">
          <Clock className="w-8 h-8 text-primary mx-auto mb-2" />
          <p className="text-sm font-medium">Conferma la prenotazione</p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <Link to="/booking/new" className="btn-primary text-base px-6 py-3">
          Prenota ora
        </Link>
        <Link to="/booking/login" className="btn-secondary text-base px-6 py-3">
          Accedi all'area personale
        </Link>
      </div>
    </div>
  )
}
