import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = ["url", "submit", "form"]
  static values = { originalButtonText: String }

  connect() {
    this.originalButtonTextValue = this.submitTarget.textContent
    this.originalButtonHTML = this.submitTarget.innerHTML
  }

  fillExampleUrl(event) {
    event.preventDefault()
    const url = event.currentTarget.dataset.url
    this.urlTarget.value = url
    this.urlTarget.focus()
  }

  validateUrl() {
    const url = this.urlTarget.value.trim()
    if (url && !this.isValidUrl(url)) {
      this.urlTarget.setCustomValidity('Please enter a valid HTTP or HTTPS URL')
    } else {
      this.urlTarget.setCustomValidity('')
    }
  }

  submit(event) {
    const url = this.urlTarget.value.trim()
    if (!url || !this.isValidUrl(url)) {
      event.preventDefault()
      this.urlTarget.focus()
      return false
    }

    this.showDownloadMessage()
  }

  showDownloadMessage() {
    const messageDiv = document.createElement('div')
    messageDiv.className = 'mt-4 bg-blue-50 border-l-4 border-blue-400 p-4 rounded-md shadow-sm'
    messageDiv.innerHTML = `
      <div class="flex">
        <div class="flex-shrink-0">
          <svg class="h-5 w-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"></path>
          </svg>
        </div>
        <div class="ml-3">
          <p class="text-sm text-blue-700 font-medium">PDF generation started! Your download should begin automatically in 3-4 seconds.</p>
        </div>
      </div>
    `

    this.formTarget.parentNode.insertBefore(messageDiv, this.formTarget.nextSibling)

    setTimeout(() => {
      if (messageDiv.parentNode) {
        messageDiv.parentNode.removeChild(messageDiv)
      }
    }, 8000)
  }

  isValidUrl(string) {
    try {
      const url = new URL(string)
      return url.protocol === 'http:' || url.protocol === 'https:'
    } catch (_) {
      return false
    }
  }
}
