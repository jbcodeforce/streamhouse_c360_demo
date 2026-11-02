import { Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import HomePage from './pages/HomePage'
import CustomersPage from './pages/CustomersPage'
import CustomerDetailPage from './pages/CustomerDetailPage'
import CustomerFormPage from './pages/CustomerFormPage'
import AccountDetailPage from './pages/AccountDetailPage'
import AccountFormPage from './pages/AccountFormPage'
import TransactionsPage from './pages/TransactionsPage'
import TransactionDetailPage from './pages/TransactionDetailPage'
import TransactionFormPage from './pages/TransactionFormPage'
import GeneratedTransactionsPage from './pages/GeneratedTransactionsPage'
import DataProductsPage from './pages/DataProductsPage'
import StatementGraphPage from './pages/StatementGraphPage'
import AnalyticsPage from './pages/AnalyticsPage'
import CEPPage from './pages/CEPPage'
import ChatPage from './pages/ChatPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/customers/new" element={<CustomerFormPage />} />
        <Route path="/customers/:id" element={<CustomerDetailPage />} />
        <Route path="/customers/:id/edit" element={<CustomerFormPage />} />
        <Route path="/accounts/new" element={<AccountFormPage />} />
        <Route path="/accounts/:id" element={<AccountDetailPage />} />
        <Route path="/accounts/:id/edit" element={<AccountFormPage />} />
        <Route path="/transactions" element={<TransactionsPage />} />
        <Route path="/transactions/new" element={<TransactionFormPage />} />
        <Route path="/transactions/generated" element={<GeneratedTransactionsPage />} />
        <Route path="/transactions/:id" element={<TransactionDetailPage />} />
        <Route path="/data-products" element={<DataProductsPage />} />
        <Route path="/data-products/:id" element={<StatementGraphPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/cep" element={<CEPPage />} />
        <Route path="/chat" element={<ChatPage />} />
      </Route>
    </Routes>
  )
}
