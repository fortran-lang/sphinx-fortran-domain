module math_utils
  !> This module provides utilities for mathematical operations
  implicit none

  contains

  !# Preceding doc.
  !> Adds two integers and returns the result
  !> but the comment continues in the next line
  subroutine add_integers(a, b, c)

    !> The first integer to add
    integer, intent(in) :: a   
    !> The second integer to add
    integer, intent(in) :: b   
    !> The result of the addition
    integer, intent(out) :: c  
    c = a + b
  end subroutine add_integers

  !> Multiplies two real numbers and returns the result
  elemental function multiply_reals(x, y) result(res)
    real, intent(in) :: x , y  !> The real numbers to multiply
    real :: res  !> The result of the multiplication
    res = x * y
  end function multiply_reals

  !> Norm of array
  pure function norm_array(array) result(res)
    real, intent(in) :: array(:)  !> The real numbers to multiply
    real :: res  !> The result of the multiplication
    res = norm2(array)
  end function norm_array

end module math_utils