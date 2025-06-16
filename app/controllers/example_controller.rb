require "faker"

class ExampleController < ApplicationController
  def index
    @name = Faker::Name.name
    @email = Faker::Internet.email
    @phone = Faker::PhoneNumber.phone_number
    @address = Faker::Address.full_address
    @city = Faker::Address.city
    @state = Faker::Address.state
    @zip = Faker::Address.zip_code
  end
end
