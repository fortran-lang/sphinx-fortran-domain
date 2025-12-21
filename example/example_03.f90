!> Complex example module with multiple entities for selective documentation
module math_utilities
    implicit none
    private
    
    public :: vector_type, matrix_type
    public :: vector_add, vector_subtract, vector_magnitude
    public :: matrix_multiply, matrix_transpose
    public :: PI, E
    
    !> Mathematical constant PI
    real, parameter :: PI = 3.14159265359
    
    !> Mathematical constant E  
    real, parameter :: E = 2.71828182846
    
    !> 3D vector type for mathematical operations
    type :: vector_type
        real :: x = 0.0 !> X component
        real :: y = 0.0 !> Y component
        real :: z = 0.0 !> Z component
    contains
        procedure :: normalize => vector_normalize
        procedure :: cross => vector_cross_product
    end type vector_type
    
    !> 3x3 matrix type for linear algebra operations
    type :: matrix_type
        !> Matrix elements stored in column-major order
        real :: elements(3,3) = 0.0
    contains
        procedure :: determinant => matrix_determinant
        procedure :: inverse => matrix_inverse
    end type matrix_type
    
contains

    !> Add two vectors component-wise
    !>
    !> .. math:: \vec{c} = \vec{a} + \vec{b} = (a_x + b_x, a_y + b_y, a_z + b_z)
    !>
    pure function vector_add(a, b) result(c)
        type(vector_type), intent(in) :: a !> First vector
        type(vector_type), intent(in) :: b !> Second vector  
        type(vector_type) :: c !> Result vector
        
        c%x = a%x + b%x
        c%y = a%y + b%y
        c%z = a%z + b%z
    end function vector_add
    
    !> Subtract two vectors component-wise
    pure function vector_subtract(a, b) result(c)
        !> First vector
        type(vector_type), intent(in) :: a
        !> Second vector
        type(vector_type), intent(in) :: b
        !> Result vector
        type(vector_type) :: c
        
        c%x = a%x - b%x
        c%y = a%y - b%y
        c%z = a%z - b%z
    end function vector_subtract
    
    !> Calculate magnitude of a vector.
    !>
    !> The magnitude is :math:`|\vec{v}| = \sqrt{x^2 + y^2 + z^2}`.
    pure function vector_magnitude(v) result(mag)
        !> Input vector
        type(vector_type), intent(in) :: v
        !> Magnitude
        real :: mag
        
        mag = sqrt(v%x**2 + v%y**2 + v%z**2)
    end function vector_magnitude
    
    !> Multiply two 3x3 matrices
    pure function matrix_multiply(a, b) result(c)
        type(matrix_type), intent(in) :: a !> First matrix
        type(matrix_type), intent(in) :: b !> Second matrix
        type(matrix_type) :: c !> Result matrix
        
        integer :: i, j, k
        
        do i = 1, 3
            do j = 1, 3
                c%elements(i,j) = 0.0
                do k = 1, 3
                    c%elements(i,j) = c%elements(i,j) + a%elements(i,k) * b%elements(k,j)
                end do
            end do
        end do
    end function matrix_multiply
    
    !> Transpose a 3x3 matrix
    pure function matrix_transpose(a) result(b)
        type(matrix_type), intent(in) :: a !> Input matrix
        type(matrix_type) :: b !> Transposed matrix
        
        integer :: i, j
        
        do i = 1, 3
            do j = 1, 3
                b%elements(i,j) = a%elements(j,i)
            end do
        end do
    end function matrix_transpose
    
    !> Private helper function (not publicly exported)
    pure function vector_internal_helper(x) result(y)
        !> Input value
        real, intent(in) :: x
        !> Output value
        real :: y
        
        y = x * 2.0
    end function vector_internal_helper
    
    !> Normalize vector to unit length (type-bound procedure)
    !>
    !> .. math:: \hat{v} = \frac{\vec{v}}{|\vec{v}|}
    !>
    pure subroutine vector_normalize(this)
        !> Vector to normalize
        class(vector_type), intent(inout) :: this
        real :: mag
        
        mag = sqrt(this%x**2 + this%y**2 + this%z**2)
        if (mag > 0.0) then
            this%x = this%x / mag
            this%y = this%y / mag  
            this%z = this%z / mag
        end if
    end subroutine vector_normalize
    
    !> Calculate cross product of two vectors (type-bound procedure)
    pure function vector_cross_product(this, other) result(cross)
        !> First vector  
        class(vector_type), intent(in) :: this
        !> Second vector
        type(vector_type), intent(in) :: other
        !> Cross product result
        type(vector_type) :: cross
        
        cross%x = this%y * other%z - this%z * other%y
        cross%y = this%z * other%x - this%x * other%z
        cross%z = this%x * other%y - this%y * other%x
    end function vector_cross_product
    
    !> Calculate matrix determinant (type-bound procedure)
    pure function matrix_determinant(this) result(det)
        !> Matrix instance
        class(matrix_type), intent(in) :: this
        !> Determinant value
        real :: det
        
        det = this%elements(1,1) * (this%elements(2,2) * this%elements(3,3) - this%elements(2,3) * this%elements(3,2)) &
            - this%elements(1,2) * (this%elements(2,1) * this%elements(3,3) - this%elements(2,3) * this%elements(3,1)) &
            + this%elements(1,3) * (this%elements(2,1) * this%elements(3,2) - this%elements(2,2) * this%elements(3,1))
    end function matrix_determinant
    
    !> Calculate matrix inverse (type-bound procedure)  
    pure function matrix_inverse(this) result(inv)
        !> Matrix instance
        class(matrix_type), intent(in) :: this
        !> Inverse matrix
        type(matrix_type) :: inv
        real :: det
        
        det = this%determinant()
        if (abs(det) > tiny(1.0)) then
            ! Calculate inverse using cofactor method
            ! ... (implementation details omitted for brevity)
            inv%elements = 0.0  ! Placeholder
        else
            inv%elements = 0.0  ! Singular matrix
        end if
    end function matrix_inverse

end module math_utilities

!> Simple utility functions outside of modules
program test_program
    use math_utilities
    implicit none
    
    type(vector_type) :: v1, v2, v3
    
    ! Example usage
    v1 = vector_type(1.0, 2.0, 3.0)
    v2 = vector_type(4.0, 5.0, 6.0)
    v3 = vector_add(v1, v2)
    
end program test_program